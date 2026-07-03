"""Rename legacy livelib_search files to {fantlab_id}_{title}.html format."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rapidfuzz import fuzz

from bookfinder.models import BookRecord
from bookfinder.normalize import normalize_title

OUT = ROOT / "data" / "processed"
SEARCH_DIR = ROOT / "data" / "raw" / "livelib_search"


def load_fantlab() -> list[BookRecord]:
    books: list[BookRecord] = []
    for item in json.loads((OUT / "fantlab_books.json").read_text(encoding="utf-8")):
        item = dict(item)
        item.pop("normalized_score", None)
        books.append(BookRecord(**item))
    return books


def fantlab_for_legacy(path: Path, books: list[BookRecord], by_id: dict[str, BookRecord]) -> BookRecord | None:
    prefix = path.stem.split("_", 1)[0]
    if prefix in by_id:
        return by_id[prefix]

    parts = path.stem.split("_", 1)
    if len(parts) < 2:
        return None

    hint = parts[1].replace("_", " ")
    best = max(
        books,
        key=lambda fl: fuzz.token_sort_ratio(normalize_title(fl.title), normalize_title(hint)),
    )
    if fuzz.token_sort_ratio(normalize_title(best.title), normalize_title(hint)) >= 85:
        return best
    return None


def main() -> None:
    books = load_fantlab()
    by_id = {b.external_id: b for b in books}
    renamed = skipped = 0

    for path in sorted(SEARCH_DIR.glob("*.html")):
        prefix = path.stem.split("_", 1)[0]
        if prefix in by_id:
            continue

        fl = fantlab_for_legacy(path, books, by_id)
        if fl is None:
            skipped += 1
            continue

        safe = "".join(ch if ch.isalnum() else "_" for ch in fl.title)[:60]
        target = SEARCH_DIR / f"{fl.external_id}_{safe}.html"
        if target.exists():
            continue

        path.rename(target)
        renamed += 1
        print(f"renamed -> {target.name}")

    print(f"renamed {renamed}, skipped {skipped}")


if __name__ == "__main__":
    main()
