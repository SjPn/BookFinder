"""Compact runtime catalog files for low-memory deployment."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

INDEX_FIELDS = (
    "id",
    "title",
    "authors",
    "genres",
    "year",
    "aggregate_rating",
    "source_origin",
    "download_url",
    "fb2_local",
    "fantlab",
    "livelib",
    "fantasy_worlds",
    "kubikus",
    "bookmix",
    "loveread",
)

_TOKEN_SPLIT = re.compile(r"[\s+.,;:!?\-\"«»()\[\]/]+")


def normalize_search_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("+", " ")
    return re.sub(r"\s+", " ", text).strip().casefold()


def build_index_entry(work: dict) -> dict:
    entry = {key: work[key] for key in INDEX_FIELDS if key in work}
    entry["search_blurb"] = (work.get("description") or "")[:300]
    return entry


def write_runtime_catalog(works: list[dict], out_dir: Path) -> dict:
    index: list[dict] = []
    details: dict[str, dict] = {}
    genre_counts: dict[str, int] = {}

    for work in works:
        index.append(build_index_entry(work))
        work_id = work["id"]
        if work.get("description"):
            details[work_id] = {
                "description": work["description"],
                "description_source": work.get("description_source"),
            }
        for genre in work.get("genres", []):
            if genre:
                genre_counts[genre] = genre_counts.get(genre, 0) + 1

    dump = lambda payload: json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "works_index.json").write_text(dump(index), encoding="utf-8")
    (out_dir / "works_details.json").write_text(dump(details), encoding="utf-8")

    total = len(index) or 1
    genres = [
        {
            "name": name,
            "count": count,
            "weight": round(count / total, 4),
        }
        for name, count in sorted(genre_counts.items(), key=lambda item: item[0].casefold())
    ]
    (out_dir / "genres.json").write_text(dump(genres), encoding="utf-8")

    return {
        "index_bytes": (out_dir / "works_index.json").stat().st_size,
        "details_bytes": (out_dir / "works_details.json").stat().st_size,
        "genres_bytes": (out_dir / "genres.json").stat().st_size,
        "works": len(index),
        "with_description": len(details),
        "genres": len(genres),
    }
