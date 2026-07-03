"""Fetch FW book pages for catalog entries missing cache."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.http_client import RateLimitedClient
from bookfinder.parsers import fantasy_worlds as fw
from bookfinder.stable_fetch import fetch_text

OUT = ROOT / "data" / "processed"
BOOKS_DIR = ROOT / "data" / "raw" / "fw_books"


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    catalog_path = OUT / "fw_catalog.json"
    if not catalog_path.exists():
        raise SystemExit("fw_catalog.json missing")

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)

    pending = [
        str(book["id"])
        for book in catalog
        if not (BOOKS_DIR / f"{book['id']}.html").exists()
    ]
    if args.limit:
        pending = pending[: args.limit]

    print(f"pending {len(pending)}")
    ok = fail = 0

    with RateLimitedClient(delay_sec=None, warmup=True) as client:
        for idx, book_id in enumerate(pending, start=1):
            url = fw.book_url(book_id)
            path = BOOKS_DIR / f"{book_id}.html"
            try:
                fetch_text(client, url, path, referer="https://fantasy-worlds.net/lib/")
                ok += 1
                if idx % 50 == 0:
                    print(f"[{idx}] saved {ok}")
            except Exception as exc:  # noqa: BLE001
                fail += 1
                if "Circuit open" in str(exc):
                    print("circuit open, stopping batch")
                    break
                if idx % 100 == 0:
                    print(f"[{idx}] fail {book_id}: {exc}")

    print(f"done ok={ok} fail={fail}")


if __name__ == "__main__":
    main()
