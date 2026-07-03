"""Fetch ReadRate rating list pages."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.http_client import RateLimitedClient
from bookfinder.parsers import readrate as rr

OUT = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw" / "readrate"

LISTS = [
    ("most-rated", "https://readrate.com/rus/books/most-rated"),
    ("most-commented", "https://readrate.com/rus/books/most-commented"),
    ("fantasy", "https://readrate.com/rus/books/fantasy"),
    ("sci-fi", "https://readrate.com/rus/books/science-fiction"),
]


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=1.5)
    args = parser.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    all_books: list[dict] = []
    seen: set[str] = set()

    with RateLimitedClient(delay_sec=args.delay, warmup=False) as client:
        for list_id, url in LISTS:
            try:
                html = client.get_text(url, referer="https://readrate.com/")
                (RAW / f"{list_id}.html").write_text(html, encoding="utf-8")
                records = rr.parse_rating_page(html, list_id)
                for record in records:
                    if record.external_id in seen:
                        continue
                    seen.add(record.external_id)
                    all_books.append(
                        {
                            "id": record.external_id,
                            "title": record.title,
                            "authors": record.authors,
                            "url": record.url,
                            "list": list_id,
                        }
                    )
                print(f"{list_id}: {len(records)}")
            except Exception as exc:  # noqa: BLE001
                print(f"fail {list_id}: {exc}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "readrate_books.json").write_text(json.dumps(all_books, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"total unique {len(all_books)}")


if __name__ == "__main__":
    main()
