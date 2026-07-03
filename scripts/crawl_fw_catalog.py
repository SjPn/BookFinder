"""Crawl Fantasy-Worlds catalog via search.json (letters, digits, common prefixes)."""

from __future__ import annotations

import json
import string
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.http_client import RateLimitedClient
from bookfinder.parsers import fantasy_worlds as fw

OUT = ROOT / "data" / "processed"
CATALOG_PATH = OUT / "fw_catalog.json"

QUERIES = list("абвгдежзийклмнопрстуфхцчшщэюяё") + list(string.ascii_lowercase) + list(string.digits)
QUERIES += ["star", "dark", "dragon", "маг", "меч", "тень", "король", "война", "книга"]
BIGRAMS = [
    "ан", "ар", "ва", "ве", "ги", "го", "да", "де", "до", "ен", "ер", "жа", "за", "зе", "ил", "ка", "ки",
    "ла", "ле", "ли", "ло", "ма", "ме", "ми", "на", "не", "ни", "но", "об", "ор", "па", "по", "пр", "ра",
    "ре", "ри", "ро", "са", "се", "си", "ск", "ст", "та", "те", "ти", "то", "тр", "ул", "фе", "ха", "че",
    "ши", "эп", "юр", "як",
]
TRIGRAMS = [
    "ста", "тор", "ный", "ная", "ное", "ный", "кра", "при", "про", "пер", "под", "над", "без", "дра",
    "вол", "лор", "мир", "тем", "све", "тен", "чер", "бел", "кра", "зве", "луна", "ден", "ноч", "огн",
    "меч", "мор", "гор", "лес", "пут", "дор", "вой", "бит", "кор", "прин", "рыц", "маг", "вед", "кол",
    "дух", "бог", "дем", "анг", "ад", "адв", "авт", "роб", "кос", "зем", "мар", "вен", "мер", "юп",
]


def load_catalog() -> dict[str, dict]:
    if not CATALOG_PATH.exists():
        return {}
    return {str(item["id"]): item for item in json.loads(CATALOG_PATH.read_text(encoding="utf-8"))}


def save_catalog(catalog: dict[str, dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    payload = sorted(catalog.values(), key=lambda item: int(item["id"]))
    CATALOG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--bigrams", action="store_true")
    parser.add_argument("--trigrams", action="store_true")
    args = parser.parse_args()

    catalog = load_catalog()
    queries = list(QUERIES)
    if args.bigrams:
        queries.extend(BIGRAMS)
    if args.trigrams:
        queries.extend(TRIGRAMS)

    with RateLimitedClient(delay_sec=args.delay, warmup=False) as client:
        for idx, query in enumerate(queries, start=1):
            try:
                response = client.get(
                    fw.search_url(query),
                    referer="https://fantasy-worlds.net/lib/",
                )
                data = response.json()
            except Exception as exc:  # noqa: BLE001
                print(f"[{idx}] fail {query}: {exc}")
                continue

            added = 0
            for item in data.get("books", []):
                book_id = str(item.get("id") or "")
                if not book_id or book_id in catalog:
                    continue
                record = fw.record_from_search_item(item)
                if record is None:
                    continue
                catalog[book_id] = {
                    "id": book_id,
                    "title": record.title,
                    "authors": record.authors,
                    "year": record.year,
                    "url": record.url,
                    "download_url": fw.download_url(book_id),
                }
                added += 1
            print(f"[{idx}] {query}: +{added}, total {len(catalog)}")
            time.sleep(0.1)

    save_catalog(catalog)
    print(f"saved {len(catalog)} books")


if __name__ == "__main__":
    main()
