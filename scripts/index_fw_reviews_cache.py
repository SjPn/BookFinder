"""Index Fantasy-Worlds comments from cached book pages."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.parsers.reviews import parse_fantasy_worlds_comments
from bookfinder.reviews_store import load_fw_reviews_by_id, save_fw_reviews_by_id

FW_BOOKS = ROOT / "data" / "raw" / "fw_books"


def main() -> None:
    data = load_fw_reviews_by_id()
    indexed = with_reviews = 0

    for path in FW_BOOKS.glob("*.html"):
        book_id = path.stem
        html = path.read_text(encoding="utf-8", errors="ignore")
        reviews = parse_fantasy_worlds_comments(html, book_id)
        if reviews:
            data[book_id] = reviews
            with_reviews += 1
        indexed += 1
        if indexed % 1000 == 0:
            print(f"[{indexed}] books with reviews: {with_reviews}")

    save_fw_reviews_by_id(data)
    total_reviews = sum(len(v) for v in data.values())
    print(json.dumps({"books": len(data), "with_reviews": with_reviews, "total_reviews": total_reviews}, ensure_ascii=False))


if __name__ == "__main__":
    main()
