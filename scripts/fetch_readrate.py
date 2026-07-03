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
    ("top100", "https://readrate.com/rus/ratings/top100"),
    ("bestsellers", "https://readrate.com/rus/ratings/bestsellers"),
    ("most-commented", "https://readrate.com/rus/books/most-commented"),
    ("books", "https://readrate.com/rus/books"),
]


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=1.5)
    args = parser.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    all_books: dict[str, dict] = {}

    with RateLimitedClient(delay_sec=args.delay, warmup=False) as client:
        for name, url in LISTS:
            cache = RAW / f"{name}.html"
            try:
                if cache.exists():
                    html = cache.read_text(encoding="utf-8", errors="ignore")
                else:
                    html = client.get_text(url, referer="https://readrate.com/rus/")
                    cache.write_text(html, encoding="utf-8")
                records = rr.parse_rating_page(html, name)
                for record in records:
                    all_books.setdefault(
                        record.external_id,
                        {
                            "external_id": record.external_id,
                            "title": record.title,
                            "url": record.url,
                            "lists": [],
                        },
                    )
                    if name not in all_books[record.external_id]["lists"]:
                        all_books[record.external_id]["lists"].append(name)
                print(f"{name}: {len(records)} books")
            except Exception as exc:  # noqa: BLE001
                print(f"fail {name}: {exc}")

    books = list(all_books.values())
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "readrate_books.json").write_text(json.dumps(books, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"unique {len(books)}")


if __name__ == "__main__":
    main()
