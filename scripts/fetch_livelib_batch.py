"""Fetch LiveLib search pages for FantLab books (Playwright, DDoS-Guard bypass)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.livelib_fetch import LiveLibSession, is_http_blocked
from bookfinder.models import BookRecord

OUT = ROOT / "data" / "processed"
SEARCH_DIR = ROOT / "data" / "raw" / "livelib_search"


def load_fantlab() -> list[BookRecord]:
    books: list[BookRecord] = []
    for item in json.loads((OUT / "fantlab_books.json").read_text(encoding="utf-8")):
        item = dict(item)
        item.pop("normalized_score", None)
        books.append(BookRecord(**item))
    return books


def pending_books(books: list[BookRecord], limit: int) -> list[BookRecord]:
    pending: list[BookRecord] = []
    for book in books:
        if list(SEARCH_DIR.glob(f"{book.external_id}_*.html")):
            continue
        pending.append(book)
        if limit and len(pending) >= limit:
            break
    return pending


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="0 = all pending")
    parser.add_argument("--delay", type=float, default=5.0)
    parser.add_argument("--headless", action="store_true", default=True)
    args = parser.parse_args()

    SEARCH_DIR.mkdir(parents=True, exist_ok=True)
    books = load_fantlab()
    pending = pending_books(books, args.limit)

    if is_http_blocked():
        print("LiveLib HTTP blocked earlier — using Playwright only")

    print(f"pending {len(pending)} / {len(books)}")
    ok = blocked = 0

    with LiveLibSession(headless=args.headless) as session:
        for idx, book in enumerate(pending, start=1):
            safe = "".join(ch if ch.isalnum() else "_" for ch in book.title)[:60]
            path = SEARCH_DIR / f"{book.external_id}_{safe}.html"
            author = book.authors[0] if book.authors else None

            try:
                html = session.fetch_search(book.title, author)
                if not html:
                    blocked += 1
                    print(f"[{idx}] blocked: {book.title}")
                else:
                    path.write_text(html, encoding="utf-8")
                    ok += 1
                    print(f"[{idx}] ok: {book.title}")
            except Exception as exc:  # noqa: BLE001
                blocked += 1
                print(f"[{idx}] fail: {book.title} -> {exc}")

            time.sleep(args.delay)

    print(f"saved {ok}, blocked {blocked}")


if __name__ == "__main__":
    main()
