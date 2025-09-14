from __future__ import annotations

import json
import logging
import os
from collections import Counter
from pathlib import Path

import click
from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline
from underthesea import sent_tokenize

logging.basicConfig(format="%(asctime)s - %(thread)d - %(message)s", level=logging.INFO)



def merge_entities(entities):
    
    if not entities:
        return []

    merged = []
    current_entity = entities[0]['entity'].split('-')[-1]
    current_text   = entities[0]['word']
    current_end    = entities[0]['end']

    for entity in entities[1:]:
        ent_type = entity['entity'].split('-')[-1]

        if ent_type == current_entity and (
            entity['entity'].startswith('I-') or entity['start'] == current_end
        ):
            # Add space only if there is a gap
            if entity['start'] > current_end:
                current_text += ' ' + entity['word']
            else:
                current_text += entity['word']
            current_end = entity['end']
        else:
            merged.append({'entity': current_entity, 'text': current_text})
            current_entity = ent_type
            current_text   = entity['word']
            current_end    = entity['end']

    merged.append({'entity': current_entity, 'text': current_text})
    return merged

def get_file_text(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read().strip()
    
def _reformat_ner_results(ner_results):
    entities = []
    for index, item in enumerate(ner_results):
        if item["word"].startswith("##") and index > 0:
            entities[-1]["word"] = entities[-1]["word"] + item["word"][2:]
            entities[-1]["end"] = item["end"]
        else:
            entities.append(item)
    return entities

def chunk_token(text: str, tokenizer: AutoTokenizer, max_tokens: int = 512, stride: int = 0) -> list[str]:

    tokens = tokenizer.encode(text, add_special_tokens=False)
    chunks = []

    start = 0
    while start < len(tokens):
        end = start + max_tokens
        chunk_ids = tokens[start:end]
        chunk_text = tokenizer.decode(chunk_ids, skip_special_tokens=True)
        chunks.append(chunk_text)
        if end >= len(tokens):
            break
        start = end - stride  

    return chunks

def get_ner_in_file(file_path: str, tokenizer, nlp) -> list[dict]:
    text = get_file_text(file_path)
    sentences = sent_tokenize(text)

    ner_results = []
    for sentence in sentences:
        if len(sentence) > 500:
            chunks = chunk_token(sentence, tokenizer, max_tokens=500, stride=50)
            for chunk in chunks:
                ner_results.extend(nlp(chunk))
        else:
            ner_results.extend(nlp(sentence))
    entities = _reformat_ner_results(ner_results)
    result = merge_entities(entities)
    return result

def get_txt_files(directory: str) -> list[str]:

    p = Path(directory)
    if not p.is_dir():
        raise NotADirectoryError(f"{directory!r} is not a valid directory")

    return [str(f.resolve()) for f in p.glob("*.txt")]

def get_common_ner(result_folder: str, top_k: int = 50):
    MODEL = "undertheseanlp/vietnamese-ner-v1.4.0a2"
    model_fine_tuned = AutoModelForTokenClassification.from_pretrained(MODEL)
    tokenizer = AutoTokenizer.from_pretrained(MODEL)
    nlp = pipeline("ner", model=model_fine_tuned, tokenizer=tokenizer)
    ner_result = []
    files = get_txt_files(result_folder)
    
    for file in files:
        logging.info(f"Processing file: {file}")
        ner_in_file = get_ner_in_file(file, tokenizer, nlp)
        ner_result.extend(ner_in_file)

    counter = Counter(item['text'] for item in ner_result)
    top_common = counter.most_common(top_k)
    result = [{'text': word, 'count': count} for word, count in top_common]
    save_path = os.path.join(result_folder, f"top_{top_k}_ner.json")
    
    
    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=4)
    logging.info(f"Top {top_k} named entities saved to {save_path}")

@click.command()
@click.argument("result_path", type=click.Path(exists=True, file_okay=False))
@click.option("--top-k", "-k", type=int, default=50, show_default=True,
              help="Number of top entities to extract.")
def cli(result_path, top_k):
    """
    Extract the TOP-K most common named entities from all .txt files in RESULT_PATH.

    RESULT_PATH must be a folder containing .txt files.
    """
    get_common_ner(result_path, top_k)


if __name__ == "__main__":
    cli()
    # get_common_ner("result/homepage/", top_k=50)