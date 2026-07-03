"""Backfill fw_catalog.json ratings and metadata from cached HTML pages."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.parsers import fantasy_worlds as fw

OUT = ROOT / "data" / "processed"
CATALOG_PATH = OUT / "fw_catalog.json"
BOOKS_DIR = ROOT / "data" / "raw" / "fw_books"


def main() -> None:
    catalog: dict[str, dict] = {}
    if CATALOG_PATH.exists():
        catalog = {str(item["id"]): item for item in json.loads(CATALOG_PATH.read_text(encoding="utf-8"))}

    updated = added = rated = 0

    for path in BOOKS_DIR.glob("*.html"):
        book_id = path.stem
        html = path.read_text(encoding="utf-8", errors="ignore")
        record = fw.parse_book_page(html)
        if record is None:
            continue

        fl_id = fw.extract_fantlab_id(html)
        entry = catalog.get(book_id, {
            "id": book_id,
            "title": record.title,
            "authors": record.authors,
            "year": record.year,
            "url": fw.book_url(book_id),
            "download_url": fw.download_url(book_id),
        })

        if book_id not in catalog:
            added += 1
        else:
            updated += 1

        entry["title"] = record.title or entry.get("title")
        entry["authors"] = record.authors or entry.get("authors", [])
        entry["year"] = record.year or entry.get("year")
        entry["genres"] = record.genres or entry.get("genres", [])
        if record.rating is not None:
            entry["rating"] = record.rating
            entry["votes"] = record.vote_count
            rated += 1
        if fl_id:
            entry["fantlab_id"] = fl_id

        catalog[book_id] = entry

    OUT.mkdir(parents=True, exist_ok=True)
    payload = sorted(catalog.values(), key=lambda item: int(item["id"]))
    CATALOG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "total": len(catalog),
        "added": added,
        "updated": updated,
        "with_rating": sum(1 for item in catalog.values() if item.get("rating")),
        "with_fantlab_id": sum(1 for item in catalog.values() if item.get("fantlab_id")),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
