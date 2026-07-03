"""Load and save aggregated book reviews."""

from __future__ import annotations

import json
from pathlib import Path

from bookfinder.parsers.reviews import dedupe_reviews

ROOT = Path(__file__).resolve().parents[2]
REVIEWS_DIR = ROOT / "data" / "processed" / "reviews"
FW_BY_ID = REVIEWS_DIR / "fw_by_id.json"
WORKS_FILE = REVIEWS_DIR / "works.json"


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_fw_reviews_by_id() -> dict[str, list[dict]]:
    return _load(FW_BY_ID)


def save_fw_reviews_by_id(data: dict[str, list[dict]]) -> None:
    _save(FW_BY_ID, data)


def load_work_reviews() -> dict[str, dict]:
    return _load(WORKS_FILE)


def save_work_reviews(data: dict[str, dict]) -> None:
    _save(WORKS_FILE, data)


def get_reviews_for_work(work_id: str, limit: int = 15, fw_id: str | None = None) -> dict:
    entry = load_work_reviews().get(work_id, {})
    reviews = list(entry.get("reviews") or [])

    if fw_id and len(reviews) < limit:
        fw_reviews = load_fw_reviews_by_id().get(str(fw_id), [])
        if fw_reviews:
            reviews = dedupe_reviews(reviews + fw_reviews)

    return {
        "work_id": work_id,
        "count": len(reviews),
        "reviews": reviews[:limit],
    }


def set_work_reviews(work_id: str, reviews: list[dict], sources_tried: list[str]) -> None:
    data = load_work_reviews()
    merged = dedupe_reviews(reviews)
    data[work_id] = {
        "count": len(merged),
        "sources_tried": sources_tried,
        "reviews": merged,
    }
    save_work_reviews(data)
