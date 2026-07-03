"""Scan Fantasy-Worlds book IDs and build catalog with optional page cache."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.http_client import RateLimitedClient
from bookfinder.parsers import fantasy_worlds as fw

OUT = ROOT / "data" / "processed"
BOOKS_DIR = ROOT / "data" / "raw" / "fw_books"
CATALOG_PATH = OUT / "fw_catalog.json"

POLL_RE = re.compile(r'id="poll_mark1_(\d+)"')


def load_catalog() -> dict[str, dict]:
    if not CATALOG_PATH.exists():
        return {}
    return {str(item["id"]): item for item in json.loads(CATALOG_PATH.read_text(encoding="utf-8"))}


def save_catalog(catalog: dict[str, dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    payload = sorted(catalog.values(), key=lambda item: int(item["id"]))
    CATALOG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def is_valid_book(html: str, book_id: str) -> bool:
    match = POLL_RE.search(html)
    return match is not None and match.group(1) == str(book_id)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=40_000)
    parser.add_argument("--delay", type=float, default=0.6)
    parser.add_argument("--save-pages", action="store_true")
    parser.add_argument("--flush-every", type=int, default=100)
    args = parser.parse_args()

    catalog = load_catalog()
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    found = skipped = invalid = 0

    with RateLimitedClient(delay_sec=args.delay, warmup=False) as client:
        for book_id in range(args.start, args.end + 1):
            sid = str(book_id)
            if sid in catalog and (BOOKS_DIR / f"{sid}.html").exists():
                skipped += 1
                continue

            try:
                response = client.get(
                    fw.book_url(book_id),
                    referer="https://fantasy-worlds.net/lib/",
                )
                html = response.text
            except Exception as exc:  # noqa: BLE001
                print(f"[{book_id}] fail: {exc}")
                continue

            if not is_valid_book(html, sid):
                invalid += 1
                continue

            record = fw.parse_book_page(html)
            if record is None:
                invalid += 1
                continue

            catalog[sid] = {
                "id": sid,
                "title": record.title,
                "authors": record.authors,
                "year": record.year,
                "genres": record.genres,
                "rating": record.rating,
                "votes": record.vote_count,
                "url": record.url,
                "download_url": fw.download_url(sid),
                "fantlab_id": fw.extract_fantlab_id(html),
            }
            found += 1

            if args.save_pages:
                (BOOKS_DIR / f"{sid}.html").write_text(html, encoding="utf-8")

            if found % 20 == 0:
                print(f"[{book_id}] found {found}, catalog {len(catalog)}, skipped {skipped}")

            if found and found % args.flush_every == 0:
                save_catalog(catalog)

    save_catalog(catalog)
    print(json.dumps({"found": found, "skipped": skipped, "invalid": invalid, "total": len(catalog)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
