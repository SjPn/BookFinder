"""Fetch LiveLib search pages for FantLab books not yet cached."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.http_client import RateLimitedClient
from bookfinder.models import BookRecord
from bookfinder.parsers import livelib

OUT = ROOT / "data" / "processed"
SEARCH_DIR = ROOT / "data" / "raw" / "livelib_search"


def load_fantlab() -> list[BookRecord]:
    books: list[BookRecord] = []
    for item in json.loads((OUT / "fantlab_books.json").read_text(encoding="utf-8")):
        item = dict(item)
        item.pop("normalized_score", None)
        books.append(BookRecord(**item))
    return books


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="0 = all pending")
    parser.add_argument("--delay", type=float, default=6.0)
    args = parser.parse_args()

    SEARCH_DIR.mkdir(parents=True, exist_ok=True)
    books = load_fantlab()
    pending: list[BookRecord] = []

    for book in books:
        safe = "".join(ch if ch.isalnum() else "_" for ch in book.title)[:60]
        if list(SEARCH_DIR.glob(f"{book.external_id}_*.html")):
            continue
        pending.append(book)
        if args.limit and len(pending) >= args.limit:
            break

    print(f"pending {len(pending)} / {len(books)}")
    ok = 0
    with RateLimitedClient(delay_sec=args.delay) as client:
        for idx, book in enumerate(pending, start=1):
            safe = "".join(ch if ch.isalnum() else "_" for ch in book.title)[:60]
            path = SEARCH_DIR / f"{book.external_id}_{safe}.html"
            try:
                html = client.get_text(
                    livelib.search_url(
                        book.title,
                        book.authors[0] if book.authors else None,
                    ),
                    referer="https://www.livelib.ru/",
                )
                if "DDoS-Guard" in html or len(html) < 5000:
                    print(f"[{idx}] blocked: {book.title}")
                    continue
                path.write_text(html, encoding="utf-8")
                ok += 1
                print(f"[{idx}] ok: {book.title}")
            except Exception as exc:  # noqa: BLE001
                print(f"[{idx}] fail: {book.title} -> {exc}")

    print(f"saved {ok}")


if __name__ == "__main__":
    main()
