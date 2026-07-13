"""Drop fake ceiling ratings (5/5 and lonely 10/10) and rebuild catalog aggregates."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.ratings import (
    FIVE_POINT_MAX_TRUSTED,
    TEN_POINT_CEILING,
    aggregate_from_sources,
    clean_bookmix_block,
    clean_fl_block,
    clean_fw_block,
    clean_kubikus_block,
    clean_ll_block,
    clean_loveread_block,
)
from bookfinder.runtime_catalog import write_runtime_catalog

OUT = ROOT / "data" / "processed"

CLEANERS = {
    "fantlab": clean_fl_block,
    "fantlab_link": clean_fl_block,
    "livelib": clean_ll_block,
    "fantasy_worlds": clean_fw_block,
    "kubikus": clean_kubikus_block,
    "bookmix": clean_bookmix_block,
    "loveread": clean_loveread_block,
}


def _source_triples(entry: dict) -> list[tuple[str, float, int | None]]:
    sources: list[tuple[str, float, int | None]] = []
    for key, name in (
        ("fantlab", "fantlab"),
        ("fantlab_link", "fantlab"),
        ("livelib", "livelib"),
        ("fantasy_worlds", "fantasy_worlds"),
        ("kubikus", "kubikus"),
        ("bookmix", "bookmix"),
        ("loveread", "loveread"),
    ):
        block = entry.get(key)
        if block and block.get("rating") is not None:
            sources.append((name, float(block["rating"]), block.get("votes")))
    return sources


def scrub_source_file(path: Path, *, five_point: bool) -> dict[str, int]:
    if not path.exists():
        return {"missing": 1}
    payload = json.loads(path.read_text(encoding="utf-8"))
    books = payload if isinstance(payload, list) else payload.get("books") or payload.get("items") or []
    dropped = 0
    for book in books:
        rating = book.get("rating")
        try:
            rating_f = float(rating) if rating is not None else None
        except (TypeError, ValueError):
            rating_f = None
        if rating_f is None:
            continue
        if five_point and rating_f > FIVE_POINT_MAX_TRUSTED:
            book["rating"] = None
            book.pop("vote_count", None)
            dropped += 1
        elif not five_point and rating_f >= TEN_POINT_CEILING:
            votes = book.get("vote_count") or book.get("votes")
            try:
                votes_i = int(votes) if votes is not None else 0
            except (TypeError, ValueError):
                votes_i = 0
            if votes_i < 100:
                book["rating"] = None
                dropped += 1
    if isinstance(payload, list):
        path.write_text(json.dumps(books, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"books": len(books), "dropped_ceiling": dropped}


def scrub_expanded(path: Path) -> dict[str, int]:
    works = json.loads(path.read_text(encoding="utf-8"))
    dropped = 0
    agg_changed = 0
    for entry in works:
        for key, cleaner in CLEANERS.items():
            block = entry.get(key)
            if not block:
                continue
            before = block.get("rating")
            cleaned = cleaner(block)
            if cleaned is None:
                entry.pop(key, None)
            else:
                entry[key] = cleaned
            try:
                if before is not None and (
                    (float(before) > FIVE_POINT_MAX_TRUSTED and key in {"loveread", "bookmix", "kubikus"})
                    or float(before) >= TEN_POINT_CEILING
                ):
                    if cleaned is None or cleaned.get("rating") is None:
                        dropped += 1
            except (TypeError, ValueError):
                pass

        old_agg = entry.get("aggregate_rating")
        agg = aggregate_from_sources(_source_triples(entry))
        new_agg = round(agg, 2) if agg is not None else None
        entry["aggregate_rating"] = new_agg
        if old_agg != new_agg:
            agg_changed += 1

    path.write_text(json.dumps(works, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"works": len(works), "dropped_ceiling_ratings": dropped, "aggregate_changed": agg_changed}


def main() -> None:
    stats = {
        "loveread_books": scrub_source_file(OUT / "loveread_books.json", five_point=True),
        "bookmix_books": scrub_source_file(OUT / "bookmix_books.json", five_point=True),
        "expanded": scrub_expanded(OUT / "expanded_works.json"),
    }
    works = json.loads((OUT / "expanded_works.json").read_text(encoding="utf-8"))
    stats["catalog"] = write_runtime_catalog(works, OUT)
    remaining = sum(1 for w in works if (w.get("aggregate_rating") or 0) >= 99.5)
    stats["aggregate_ge_99_5"] = remaining
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
