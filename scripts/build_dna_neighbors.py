"""Precompute DNA similarity neighbors for fast API recommendations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.book_dna import BookDNAProfile
from bookfinder.catalog import get_work
from bookfinder.dna_similarity import DNA_MODES, combined_similarity
from bookfinder.dna_store import DNA_DIR, build_index, load_index, save_neighbors

DATA = ROOT / "data" / "processed"
TOP_K = 20


def load_profiles() -> list[BookDNAProfile]:
    profiles: list[BookDNAProfile] = []
    for path in sorted(DNA_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            profiles.append(BookDNAProfile.model_validate(data))
        except (json.JSONDecodeError, ValueError):
            continue
    return profiles


def main() -> None:
    parser = argparse.ArgumentParser(description="Build dna_neighbors.json from local DNA profiles")
    parser.add_argument("--top-k", type=int, default=TOP_K, help="Neighbors per mode")
    parser.add_argument("--limit", type=int, default=0, help="Limit source profiles (0 = all)")
    parser.add_argument("--reindex", action="store_true", help="Rebuild dna_index.json first")
    args = parser.parse_args()

    if args.reindex:
        build_index()

    profiles = load_profiles()
    if args.limit > 0:
        profiles = profiles[: args.limit]
    if len(profiles) < 2:
        raise SystemExit("Need at least 2 DNA profiles in data/processed/dna/")

    genres_by_id: dict[str, set[str]] = {}
    for profile in profiles:
        work = get_work(profile.work_id) or {}
        genres_by_id[profile.work_id] = {genre.casefold() for genre in work.get("genres") or [] if genre}

    items: dict[str, dict[str, list[dict[str, float | str]]]] = {}
    for idx, base in enumerate(profiles, start=1):
        base_genres = genres_by_id.get(base.work_id, set())
        mode_rows: dict[str, list[dict[str, float | str]]] = {}
        for mode in DNA_MODES:
            scored: list[tuple[float, str]] = []
            for candidate in profiles:
                if candidate.work_id == base.work_id:
                    continue
                score = combined_similarity(
                    base,
                    candidate,
                    mode=mode,
                    left_genres=base_genres,
                    right_genres=genres_by_id.get(candidate.work_id, set()),
                )
                if score > 0.05:
                    scored.append((score, candidate.work_id))
            scored.sort(key=lambda pair: pair[0], reverse=True)
            mode_rows[mode] = [
                {"work_id": work_id, "score": round(score, 4)} for score, work_id in scored[: args.top_k]
            ]
        items[base.work_id] = mode_rows
        if idx % 25 == 0:
            print(f"processed {idx}/{len(profiles)}")

    index = load_index() or {}
    payload = {
        "version": index.get("version", 1),
        "prompt_version": index.get("prompt_version", ""),
        "count": len(items),
        "top_k": args.top_k,
        "items": items,
    }
    path = save_neighbors(payload)
    print(json.dumps({"neighbors": len(items), "path": str(path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
