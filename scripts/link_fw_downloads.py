"""Link Fantasy-Worlds download URLs to FantLab books missing FW match."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.http_client import RateLimitedClient
from bookfinder.matcher import MATCH_THRESHOLD, find_best_match
from bookfinder.models import BookRecord
from bookfinder.normalize import normalize_authors, normalize_title
from bookfinder.parsers import fantasy_worlds as fw

OUT = ROOT / "data" / "processed"
SEARCH_DIR = ROOT / "data" / "raw" / "fw_search"
LINKS_PATH = OUT / "fw_download_links.json"


def load_fantlab() -> list[BookRecord]:
    books: list[BookRecord] = []
    for item in json.loads((OUT / "fantlab_books.json").read_text(encoding="utf-8")):
        item = dict(item)
        item.pop("normalized_score", None)
        book = BookRecord(**item)
        book.normalized_title = normalize_title(book.title)
        book.normalized_authors = normalize_authors(book.authors)
        books.append(book)
    return books


def load_links() -> dict[str, dict]:
    if LINKS_PATH.exists():
        return json.loads(LINKS_PATH.read_text(encoding="utf-8"))
    return {}


def save_links(links: dict[str, dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    LINKS_PATH.write_text(json.dumps(links, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--fetch-missing", action="store_true")
    args = parser.parse_args()

    links = load_links()
    fantlab = load_fantlab()
    pending = [book for book in fantlab if book.external_id not in links]

    print(f"pending {len(pending)} / {len(fantlab)}")

    with RateLimitedClient(delay_sec=args.delay, warmup=False) as client:
        for idx, book in enumerate(pending, start=1):
            search_path = SEARCH_DIR / f"{book.external_id}.json"
            candidates: list[BookRecord] = []

            if search_path.exists():
                candidates = fw.parse_search_json(search_path.read_text(encoding="utf-8"))
            elif args.fetch_missing:
                try:
                    query = f"{book.authors[0]} {book.title}" if book.authors else book.title
                    data = client.get_json(
                        fw.search_url(query),
                        referer="https://fantasy-worlds.net/lib/",
                    )
                    SEARCH_DIR.mkdir(parents=True, exist_ok=True)
                    search_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                    candidates = fw.parse_search_json(data)
                except Exception as exc:  # noqa: BLE001
                    print(f"[{idx}] search fail {book.title}: {exc}")
                    continue

            for candidate in candidates:
                candidate.normalized_title = normalize_title(candidate.title)
                candidate.normalized_authors = normalize_authors(candidate.authors)

            match = find_best_match(book, candidates, MATCH_THRESHOLD) if candidates else None
            if match:
                fw_book = match.livelib  # type: ignore[assignment]
                links[book.external_id] = {
                    "fw_id": fw_book.external_id,
                    "title": fw_book.title,
                    "download_url": fw.download_url(fw_book.external_id),
                    "url": fw.book_url(fw_book.external_id),
                    "match_score": round(match.score, 3),
                }
                print(f"[{idx}] linked: {book.title} -> {fw_book.external_id}")
            else:
                links[book.external_id] = {"fw_id": None}
                print(f"[{idx}] no match: {book.title}")

            if idx % 25 == 0:
                save_links(links)

    save_links(links)
    matched = sum(1 for value in links.values() if value.get("fw_id"))
    print(f"linked {matched} / {len(links)}")


if __name__ == "__main__":
    main()
