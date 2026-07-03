"""Download Fantasy-Worlds book pages for already cached search results."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.http_client import RateLimitedClient
from bookfinder.matcher import find_best_match
from bookfinder.models import BookRecord
from bookfinder.normalize import normalize_authors, normalize_title
from bookfinder.parsers import fantasy_worlds as fw

OUT = ROOT / "data" / "processed"
SEARCH_DIR = ROOT / "data" / "raw" / "fw_search"
BOOKS_DIR = ROOT / "data" / "raw" / "fw_books"


def load_fantlab() -> dict[str, BookRecord]:
    books: dict[str, BookRecord] = {}
    for item in json.loads((OUT / "fantlab_books.json").read_text(encoding="utf-8")):
        item = dict(item)
        item.pop("normalized_score", None)
        book = BookRecord(**item)
        books[book.external_id] = book
    return books


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--delay", type=float, default=2.0)
    args = parser.parse_args()

    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    fantlab = load_fantlab()
    pending: list[tuple[BookRecord, BookRecord]] = []

    for path in sorted(SEARCH_DIR.glob("*.json")):
        fl = fantlab.get(path.stem)
        if fl is None:
            continue
        candidates = fw.parse_search_json(path.read_text(encoding="utf-8"))
        for candidate in candidates:
            candidate.normalized_title = normalize_title(candidate.title)
            candidate.normalized_authors = normalize_authors(candidate.authors)
        match = find_best_match(fl, candidates) if candidates else None
        if not match:
            continue
        fw_book = match.livelib  # type: ignore[assignment]
        page_path = BOOKS_DIR / f"{fw_book.external_id}.html"
        if page_path.exists():
            continue
        pending.append((fl, fw_book))
        if args.limit and len(pending) >= args.limit:
            break

    print(f"pending pages {len(pending)}")
    ok = 0
    with RateLimitedClient(delay_sec=args.delay, warmup=False) as client:
        for idx, (fl, fw_book) in enumerate(pending, start=1):
            try:
                html = client.get(
                    fw.book_url(fw_book.external_id),
                    referer="https://fantasy-worlds.net/lib/",
                ).text
                (BOOKS_DIR / f"{fw_book.external_id}.html").write_text(html, encoding="utf-8")
                ok += 1
                print(f"[{idx}] ok: {fl.title} -> {fw_book.external_id}")
            except Exception as exc:  # noqa: BLE001
                print(f"[{idx}] fail: {fl.title} -> {exc}")

    print(f"saved pages {ok}")


if __name__ == "__main__":
    main()
