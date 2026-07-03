"""Persist portal user ratings (anonymous client id, no auth)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RATINGS_PATH = ROOT / "data" / "processed" / "user_ratings.json"


def _load_raw() -> dict:
    if not RATINGS_PATH.exists():
        return {"ratings": []}
    return json.loads(RATINGS_PATH.read_text(encoding="utf-8"))


def _save_raw(data: dict) -> None:
    RATINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RATINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_user_rating(user_id: str, work_id: str) -> int | None:
    for row in _load_raw().get("ratings", []):
        if row.get("user_id") == user_id and row.get("work_id") == work_id:
            rating = row.get("rating")
            if isinstance(rating, (int, float)):
                return int(rating)
    return None


def set_user_rating(user_id: str, work_id: str, rating: int) -> dict:
    if not user_id or not work_id:
        raise ValueError("user_id and work_id required")
    if rating < 1 or rating > 10:
        raise ValueError("rating must be 1..10")

    data = _load_raw()
    rows: list[dict] = data.setdefault("ratings", [])
    now = datetime.now(timezone.utc).isoformat()
    updated = False
    for row in rows:
        if row.get("user_id") == user_id and row.get("work_id") == work_id:
            row["rating"] = rating
            row["updated_at"] = now
            updated = True
            break
    if not updated:
        rows.append(
            {
                "user_id": user_id,
                "work_id": work_id,
                "rating": rating,
                "updated_at": now,
            }
        )
    _save_raw(data)
    return {"user_id": user_id, "work_id": work_id, "rating": rating, "updated_at": now}


def delete_user_rating(user_id: str, work_id: str) -> bool:
    data = _load_raw()
    rows = data.get("ratings", [])
    new_rows = [r for r in rows if not (r.get("user_id") == user_id and r.get("work_id") == work_id)]
    if len(new_rows) == len(rows):
        return False
    data["ratings"] = new_rows
    _save_raw(data)
    return True


def work_user_stats(work_id: str) -> dict:
    values = [
        int(row["rating"])
        for row in _load_raw().get("ratings", [])
        if row.get("work_id") == work_id and isinstance(row.get("rating"), (int, float))
    ]
    if not values:
        return {"count": 0, "average": None}
    return {"count": len(values), "average": round(sum(values) / len(values), 2)}
