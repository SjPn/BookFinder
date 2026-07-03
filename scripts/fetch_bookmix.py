"""Fetch BookMix list pages and book ratings."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.bookmix_client import fetch_text
from bookfinder.parsers import bookmix as bm

OUT = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw" / "bookmix"

LISTS = [
    ("top250", "https://bookmix.ru/top-250-books.phtml"),
    ("bestbooks", "https://bookmix.ru/bestbooks.phtml"),
    ("books", "https://bookmix.ru/books/"),
    ("best2026", "https://bookmix.ru/bestbooksyear.phtml"),
    ("best2026_p2", "https://bookmix.ru/bestbooksyear.phtml?cid=-1&begin=10&num_point=10&num_points=10"),
    ("best2026_p3", "https://bookmix.ru/bestbooksyear.phtml?cid=-1&begin=20&num_point=10&num_points=10"),
    ("fantasy_tag", "https://bookmix.ru/booktag.phtml?keytag=%D1%84%D0%B0%D0%BD%D1%82%D0%B0%D1%81%D1%82%D0%B8%D0%BA%D0%B0"),
    ("fantasy_tag2", "https://bookmix.ru/booktag.phtml?keytag=%D1%84%D1%8D%D0%BD%D1%82%D0%B5%D0%B7%D0%B8"),
]


def record_dict(record) -> dict:
    data = asdict(record)
    data["normalized_score"] = record.normalized_score
    return data


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--book-limit", type=int, default=300)
    parser.add_argument("--delay", type=float, default=2.0)
    args = parser.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    by_id: dict[str, dict] = {}
    out_path = OUT / "bookmix_books.json"
    if out_path.exists():
        for item in json.loads(out_path.read_text(encoding="utf-8")):
            by_id[str(item["external_id"])] = item

    for list_id, url in LISTS:
        print(f"list {list_id}")
        cache = RAW / f"list_{list_id}.html"
        try:
            html = cache.read_text(encoding="utf-8") if cache.exists() else fetch_text(url, delay=args.delay)
            cache.write_text(html, encoding="utf-8")
            for record in bm.parse_list_page(html):
                entry = record_dict(record)
                entry.setdefault("lists", []).append(list_id)
                prev = by_id.get(record.external_id)
                if prev:
                    entry["lists"] = sorted(set(prev.get("lists", []) + entry["lists"]))
                by_id[record.external_id] = entry
        except Exception as exc:  # noqa: BLE001
            print(f"  fail {list_id}: {exc}")

    pending = sorted(by_id.keys(), key=int)
    if args.book_limit:
        pending = pending[: args.book_limit]

    print(f"books pending {len(pending)}")
    ok = fail = 0
    for idx, book_id in enumerate(pending, start=1):
        cache = RAW / f"{book_id}.html"
        try:
            if not cache.exists():
                html = fetch_text(bm.book_url(book_id), delay=args.delay)
                cache.write_text(html, encoding="utf-8")
            else:
                html = cache.read_text(encoding="utf-8")
            record = bm.parse_book_page(html, book_id)
            if record:
                data = record_dict(record)
                data["lists"] = by_id[book_id].get("lists", [])
                by_id[book_id] = data
                ok += 1
            else:
                fail += 1
        except Exception as exc:  # noqa: BLE001
            fail += 1
            if idx % 20 == 0:
                print(f"  fail {book_id}: {exc}")
        if idx % 40 == 0:
            print(f"[{idx}] ok={ok} fail={fail}")

    books = list(by_id.values())
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "bookmix_books.json").write_text(json.dumps(books, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {len(books)} (pages ok={ok}, fail={fail})")


if __name__ == "__main__":
    main()
