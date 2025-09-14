from __future__ import annotations

import asyncio
import logging
import os
import re
from enum import Enum

import aiohttp
import click
import requests
from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup

logging.basicConfig(format="%(asctime)s - %(thread)d - %(message)s", level=logging.INFO)

BASE_URL = "https://baomoi.com"

HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9,vi;q=0.8",
    "dnt": "1",
    "priority": "u=1, i",
    "referer": BASE_URL,
    "sec-ch-ua": '"Chromium";v="140", "Not=A?Brand";v="24", "Microsoft Edge";v="140"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0",
    "x-nextjs-data": "1",
}

LIMITER = AsyncLimiter(10, 1)  # 10 requests per second

class Category(Enum):
    THE_GIOI = "the-gioi"
    XA_HOI = "xa-hoi"
    VAN_HOA = "van-hoa"
    KINH_TE = "kinh-te"
    GIAO_DUC = "giao-duc"
    THE_THAO = "the-thao"
    GIAI_TRI = "giai-tri"
    PHAP_LUAT = "phap-luat"
    CONG_NGHE = "khoa-hoc-cong-nghe"
    KHOA_HOC = "khoa-hoc"
    DOI_SONG = "doi-song"
    XE_CO = "xe-co"
    NHA_DAT = "nha-dat"

class ProccessPostDetail:
    def __init__(self, soup: BeautifulSoup):
        self.soup = soup

    @property
    def content(self) -> str:
        content_wrapper = self.soup.find("div", attrs={"class": "content-wrapper"})
        try:
            description = content_wrapper.find("h3").get_text(strip=True)
        except AttributeError:  # Some posts don't have description
            description = ""
        paragraphs = content_wrapper.find_all("p", attrs={"class": "text"})
        content = "\n".join(
            [
                p.text
                for p in paragraphs
                if not any(
                    c in ["body-author", "media-caption"]  # skip author and caption
                    for c in (p.get("class") or [])
                )
            ]
        )
        return f"{description}\n{content}"

    @property
    def title(self) -> str:
        content_wrapper = self.soup.find("div", attrs={"class": "content-wrapper"})
        title = content_wrapper.find("h1").get_text(strip=True)
        return title

def _get_build_id() -> str:
    response = requests.get(BASE_URL, headers=HEADERS)
    if response.status_code == 200:
        match = re.search(r'"buildId"\s*:\s*"([^"]+)"', response.text)
        if match:
            return match.group(1)
        else:
            raise Exception("buildId not found in the page")
    else:
        raise Exception(f"Failed to get buildId: {response.status_code}")


def normalize_filename(name: str, max_length: int = 255) -> str:
    """
    Normalize a string to a safe filename.
    """

    s = name.lower().strip()
    s = re.sub(r'[\\/:*?"<>|]+', "_", s)
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"__+", "_", s)

    if not s:
        s = "untitled"

    return s[:max_length]


def get_posts(page: int, build_id: str, category: Category | None) -> dict:
    params = {
        "page": str(page),
    }
    if category:
        url = f"{BASE_URL}/_next/data/{build_id}/category/{category.value}/{page}.json?slug={category.value}&page={page}"
    else:
        url = f"{BASE_URL}/_next/data/{build_id}/home/{page}.json?page={page}"
    response = requests.get(
        url,
        params=params,
        headers=HEADERS,
    )
    result = []
    if response.status_code == 200:
        for section in response.json()["pageProps"]["resp"]["data"]["content"][
            "sections"
        ]:
            result.extend(
                section.get("items", [])
            )  # some sections in homepage may not have 'items'
        return result
    else:
        raise Exception(f"Failed to fetch data: {response.status_code}")

def get_post_urls(post_count: int = 200, category: Category | None = None) -> set[str]:
    build_id = _get_build_id()

    urls = set()
    page = 1
    while len(urls) < post_count:
        logging.info(f"Fetching page {page}...")
        data = get_posts(page, build_id, category)
        for d in data:
            try:
                url = d["url"]
            except KeyError:  # skip ads like item {'zoneId': 'BaoMoi_MastheadInline_2', 'id': 'BaoMoi_MastheadInline_2', 'elId': 'BaoMoi_MastheadInline_2', 'type': 'adBanner'}
                continue
            urls.add(BASE_URL + url)
            if len(urls) >= post_count:
                break
        page += 1
    return urls


async def get_post_detail(session: aiohttp.ClientSession, url: str, path: str):
    async with LIMITER:
        async with session.get(url, headers=HEADERS) as response:
            logging.info(f"Fetching {url}")
            if response.status != 200:
                raise Exception(f"Failed to fetch data: {response.status}")

            html = await response.text()
            soup = BeautifulSoup(html, "html.parser")

            ppd = ProccessPostDetail(soup)
            title = ppd.title
            file_name = normalize_filename(title)
            content = ppd.content
            file_path = os.path.join(path, f"{file_name}.txt")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)


async def download_all(urls: list[str], path: str):
    """Run multiple get_post_detail tasks concurrently."""
    async with aiohttp.ClientSession() as session:
        tasks = [get_post_detail(session, url, path) for url in urls]
        await asyncio.gather(*tasks)


@click.command()
@click.option(
    "--post-count",
    "-p",
    type=int,
    default=200,
    show_default=True,
    help="Number of posts to fetch",
)
@click.option(
    "--category",
    "-c",
    type=str,
    default=None,
    help="Category slug (e.g. 'xa-hoi', 'van-hoa'). Default: homepage",
)
def cli(post_count: int, category: str | None):
    cat_enum = None
    if category:
        try:
            cat_enum = Category(category)
            saving_path = os.path.join("result", cat_enum.value)
        except ValueError:
            valid = ", \n".join(c.value for c in Category)
            raise click.BadParameter(
                f"Invalid category '{category}'. Valid options: {valid}"
            )
    else:
        saving_path = os.path.join("result", "homepage")
    os.makedirs(saving_path, exist_ok=True)

    urls = get_post_urls(post_count, cat_enum)

    asyncio.run(download_all(urls=list(urls), path=saving_path))
    click.echo(f"Downloaded {len(urls)} posts to {saving_path}")


if __name__ == "__main__":
    cli()

    # urls = get_post_urls()

    # asyncio.run(download_all(urls=list(urls), path="result"))
