"""Fetch Fantasy-Worlds search results and optional book pages for FantLab books."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.http_client import RateLimitedClient
from bookfinder.matcher import find_best_match
from bookfinder.models import BookRecord
from bookfinder.parsers import fantasy_worlds as fw

OUT = ROOT / "data" / "processed"
SEARCH_DIR = ROOT / "data" / "raw" / "fw_search"
BOOKS_DIR = ROOT / "data" / "raw" / "fw_books"


def load_fantlab() -> list[BookRecord]:
    books: list[BookRecord] = []
    for item in json.loads((OUT / "fantlab_books.json").read_text(encoding="utf-8")):
        item = dict(item)
        item.pop("normalized_score", None)
        books.append(BookRecord(**item))
    return books


def search_query(book: BookRecord) -> str:
    if book.authors:
        return f"{book.authors[0]} {book.title}"
    return book.title


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="0 = all pending")
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--fetch-pages", action="store_true", help="Download matched book pages")
    args = parser.parse_args()

    SEARCH_DIR.mkdir(parents=True, exist_ok=True)
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)

    books = load_fantlab()
    pending: list[BookRecord] = []
    for book in books:
        if (SEARCH_DIR / f"{book.external_id}.json").exists():
            continue
        pending.append(book)
        if args.limit and len(pending) >= args.limit:
            break

    print(f"pending {len(pending)} / {len(books)}")
    ok = 0
    pages = 0

    with RateLimitedClient(delay_sec=args.delay, warmup=False) as client:
        for idx, book in enumerate(pending, start=1):
            path = SEARCH_DIR / f"{book.external_id}.json"
            try:
                response = client.get(
                    fw.search_url(search_query(book)),
                    referer="https://fantasy-worlds.net/lib/",
                )
                data = response.json()
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                ok += 1

                if args.fetch_pages:
                    candidates = fw.parse_search_json(data)
                    match = find_best_match(book, candidates) if candidates else None
                    if match:
                        fw_book = match.livelib  # reused field name in MatchResult
                        page_path = BOOKS_DIR / f"{fw_book.external_id}.html"
                        if not page_path.exists():
                            html = client.get(
                                fw.book_url(fw_book.external_id),
                                referer="https://fantasy-worlds.net/lib/",
                            ).text
                            page_path.write_text(html, encoding="utf-8")
                            pages += 1

                print(f"[{idx}] ok: {book.title}")
            except Exception as exc:  # noqa: BLE001
                print(f"[{idx}] fail: {book.title} -> {exc}")

    print(f"saved search {ok}, pages {pages}")


if __name__ == "__main__":
    main()
