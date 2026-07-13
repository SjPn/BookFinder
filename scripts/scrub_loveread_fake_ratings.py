"""Strip fake LoveRead 5.0 ratings and view-as-votes; rebuild aggregates + catalog."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.ratings import (
    LOVEREAD_MAX_TRUSTED,
    aggregate_from_sources,
    clean_loveread_block,
)
from bookfinder.runtime_catalog import write_runtime_catalog

OUT = ROOT / "data" / "processed"


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


def scrub_loveread_books(path: Path) -> dict[str, int]:
    if not path.exists():
        return {"missing": 1}
    payload = json.loads(path.read_text(encoding="utf-8"))
    books = payload if isinstance(payload, list) else payload.get("books") or payload.get("items") or []
    dropped_rating = 0
    cleared_votes = 0
    for book in books:
        if book.get("vote_count") is not None:
            book["vote_count"] = None
            cleared_votes += 1
        rating = book.get("rating")
        try:
            rating_f = float(rating) if rating is not None else None
        except (TypeError, ValueError):
            rating_f = None
        if rating_f is not None and rating_f > LOVEREAD_MAX_TRUSTED:
            book["rating"] = None
            dropped_rating += 1
    if isinstance(payload, list):
        path.write_text(json.dumps(books, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"books": len(books), "dropped_rating_5": dropped_rating, "cleared_votes": cleared_votes}


def scrub_expanded(path: Path) -> dict[str, int]:
    works = json.loads(path.read_text(encoding="utf-8"))
    dropped_rating = 0
    kept_link = 0
    agg_changed = 0
    for entry in works:
        lr = entry.get("loveread")
        if lr:
            before = lr.get("rating")
            cleaned = clean_loveread_block(lr)
            if cleaned is None:
                entry.pop("loveread", None)
            else:
                entry["loveread"] = cleaned
                kept_link += 1
            try:
                if before is not None and float(before) > LOVEREAD_MAX_TRUSTED:
                    dropped_rating += 1
            except (TypeError, ValueError):
                pass

        old_agg = entry.get("aggregate_rating")
        agg = aggregate_from_sources(_source_triples(entry))
        new_agg = round(agg, 2) if agg is not None else None
        entry["aggregate_rating"] = new_agg
        if old_agg != new_agg:
            agg_changed += 1

    path.write_text(json.dumps(works, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "works": len(works),
        "dropped_loveread_5": dropped_rating,
        "loveread_links_kept": kept_link,
        "aggregate_changed": agg_changed,
    }


def main() -> None:
    lr_stats = scrub_loveread_books(OUT / "loveread_books.json")
    exp_stats = scrub_expanded(OUT / "expanded_works.json")
    catalog = write_runtime_catalog(
        json.loads((OUT / "expanded_works.json").read_text(encoding="utf-8")),
        OUT,
    )
    print(
        json.dumps(
            {"loveread_books": lr_stats, "expanded": exp_stats, "catalog": catalog},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
