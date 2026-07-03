"""Attach cached FW reviews to catalog works (no network)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.parsers.reviews import dedupe_reviews
from bookfinder.reviews_store import load_fw_reviews_by_id, load_work_reviews, save_work_reviews

OUT = ROOT / "data" / "processed"


def load_works() -> list[dict]:
    for name in ("expanded_works.json", "merged_works.json"):
        path = OUT / name
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return []


def main() -> None:
    fw_cache = load_fw_reviews_by_id()
    store = load_work_reviews()
    with_reviews = 0

    for work in load_works():
        work_id = work["id"]
        reviews: list[dict] = list(store.get(work_id, {}).get("reviews") or [])
        tried = list(store.get(work_id, {}).get("sources_tried") or [])

        fw_id = (work.get("fantasy_worlds") or {}).get("id")
        if fw_id and str(fw_id) in fw_cache:
            reviews.extend(fw_cache[str(fw_id)])
            if "fantasy_worlds" not in tried:
                tried.append("fantasy_worlds")

        merged = dedupe_reviews(reviews)
        if merged:
            with_reviews += 1
        store[work_id] = {
            "count": len(merged),
            "sources_tried": tried,
            "reviews": merged[:15],
        }

    save_work_reviews(store)
    print(json.dumps({"works": len(store), "with_reviews": with_reviews}, ensure_ascii=False))


if __name__ == "__main__":
    main()
