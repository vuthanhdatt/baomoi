# Baomoi crawler and NER detection


   * [Installation](#installation)
   * [Usage](#usage)
      + [Crawling](#crawling)
      + [NER detection](#ner-detection)
   * [How it works](#how-it-works)
      + [Crawling baomoi articles](#crawling-baomoi-articles)
      + [Named Entity Recognition (NER) detection](#named-entity-recognition-ner-detection)
   * [Some thoughts](#some-thoughts)


## Installation

```bash
pip install -r requirements.txt
``` 

Note that NER detection using `AutoModelForSequenceClassification` that requires the PyTorch library. Install it varying on your system OS and CUDA version. See [PyTorch official installation guide](https://pytorch.org/get-started/locally/) to install the suitable PyTorch version on your machine. All code is testing and run on Ubuntu 22.04 with torch==2.8.0+cpu. We can use [simply NER model from underthesea](https://github.com/undertheseanlp/ner) without installing PyTorch, but the results are not good as using transformer model.

## Usage

### Crawling
```bash
python crawl.py --help
Usage: crawl.py [OPTIONS]

Options:
  -p, --post-count INTEGER  Number of posts to fetch  [default: 200]
  -c, --category TEXT       Category slug (e.g. 'xa-hoi', 'van-hoa'). Default:
                            homepage
  --help                    Show this message and exit.
```

- To crawl baomoi articles, run `python crawl.py` with options. For example, to crawl 200 articles in the "the-gioi" category:
```bash
python crawl.py --category the-gioi --post_count 200 
```
We can choose other categories and adjust number of posts to crawl. If not specify the category and number of posts, it's will crawl from hompage with 200 articles. The crawled articles are saved in the `result` folder.

### NER detection

```bash
 python name_enity_detection.py --help
Usage: name_enity_detection.py [OPTIONS] RESULT_PATH

  Extract the TOP-K most common named entities from all .txt files in
  RESULT_PATH.

  RESULT_PATH must be a folder containing .txt files.

Options:
  -k, --top-k INTEGER  Number of top entities to extract.  [default: 50]
  --help               Show this message and exit.
```
To extract named entities from the crawled articles, run `python name_enity_detection.py <result_folder>` with options, the result folder must be a folder containing .txt files. For example, to extract the top 100 named entities from the articles in the `result/the-gioi/` folder:
```bash
python name_enity_detection.py result/the-gioi/ --top-k 100
```
The result will be saved with format `top_k_ner.json` in the same input folder.

## How it works

Here, I will briefly explain how the code works. With the requirements is 

> Scrape 200 articles from baomoi.com, which were published within the last 4 days. The articles can be random or from a specific category. Return the distribution of top 50 name/entities mentioned in those articles

There are two main parts: crawling baomoi articles and named entity recognition (NER) detection.

### Crawling baomoi articles
Crawling baomoi is quite simple. They dont have any strict anti-crawling mechanism. The articles are loaded dynamically using Next.js framework. We can easily find the endpoint requests to get the articles data in JSON format by inspecting the network requests. One note is that the request endpoint contains a `build_id` parameter that changes over time. I create [`_get_build_id`](https://github.com/vuthanhdatt/baomoi/blob/main/crawl.py#L52) function to get the `build_id` by sending a request to the homepage and parsing the HTML response to find the `buildId` value in the script tag. Then loop through the pages to get the articles data until reaching the desired number of articles. The article URLs are saved in a set to avoid duplicates, using this will avoid overhead in baomoi pagination mechanism.

After getting all desired article URLs, I use asynchronous requests with `aiohttp` library to fetch the article content concurrently to speeds up the crawling process. The article content is parsed using `BeautifulSoup` to extract the main article content and save it as a text file in correspond folder. I also add rate limiting using to avoid overwhelming the server with too many requests at once although baomoi dont have strict anti-crawling mechanism, I still can get with sspeed 100 articles/s but currently limit to 10 articles/s.

### Named Entity Recognition (NER) detection
For NER detection, I use a pre-trained transformer model `undertheseanlp/vietnamese-ner-v1.4.0a2` from [Hugging Face](https://huggingface.co/undertheseanlp/vietnamese-ner-v1.4.0a2), which is fine-tuned for Vietnamese NER tasks. We can also use the simple NER model from [underthesea](https://github.com/undertheseanlp/ner) library without installing PyTorch, but after doing some testing, I see the results are not good as using transformer model. 

The script reads all text files contain ther crawled results in the specified folder, processes each file to extract named entities using the NER model, and counts the occurrences of each entity across all files. Finally, it outputs the top K most common named entities to a JSON file. 

The model is not good in long context, so i decide to split the articles into sentences and process each sentence separately to improve the accuracy of NER detection. The model is also only accept 512 tokens as input, although the sentences are usually shorter than this limit, there is some rare case that a sentence is longer than this limit, so I also chunk the long sentences into smaller chunks to ensure that each chunk is within the model's input limit.

Here the model outcome is not yet match desired expectation output, I still need to do some post-processing to merge the entities that are split into multiple parts, for example, "Hà Nội" is split into two parts "Hà" and "Nội", so I create `merge_entities` function to merge these parts into a single entity and reformat ner result which have `##` prefix in the entity text.

Finally, I count the occurrences of each entity and output the top K most common entities to a JSON file inside input folder.

## Some thoughts
- The crawling part is quite simple, in more complex scenarios, we might need to handle more anti-crawling mechanisms, such as CAPTCHAs, IP blocking, etc. In that case, we can use Selenium, rotate proxies, headers, fingerprint and other advanced technique to bypass. We might also need to implement more robust error handling and retry mechanisms to ensure the crawler can handle network issues and server errors gracefully.

- The NER detection part can be further improved by fine-tuning the model on a specific dataset if we have one, or by using ensemble methods to combine the results of multiple models for better accuracy. We can also experiment with other pre-trained models to see which one performs best for our specific use case.