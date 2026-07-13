"""Persist book DNA profiles on disk."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from bookfinder.book_dna import (
    DNA_VERSION,
    PROMPT_VERSION,
    BookDNAProfile,
    derive_tropes_from_axes,
)

ROOT = Path(__file__).resolve().parents[2]
DNA_DIR = ROOT / "data" / "processed" / "dna"
DNA_INDEX = ROOT / "data" / "processed" / "dna_index.json"
DNA_NEIGHBORS = ROOT / "data" / "processed" / "dna_neighbors.json"
DNA_PROGRESS = ROOT / "data" / "processed" / "dna_progress.json"
DNA_HEARTBEAT = ROOT / "data" / "processed" / "dna_heartbeat.json"
_UNSAFE = re.compile(r"[^\w.\-]+")


def safe_filename(work_id: str) -> str:
    return _UNSAFE.sub("_", work_id)


def profile_path(work_id: str) -> Path:
    return DNA_DIR / f"{safe_filename(work_id)}.json"


def load_profile(work_id: str) -> BookDNAProfile | None:
    path = profile_path(work_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return BookDNAProfile.model_validate(data)


def save_profile(profile: BookDNAProfile) -> Path:
    DNA_DIR.mkdir(parents=True, exist_ok=True)
    path = profile_path(profile.work_id)
    path.write_text(
        json.dumps(profile.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_progress() -> dict[str, str]:
    if not DNA_PROGRESS.exists():
        return {}
    return json.loads(DNA_PROGRESS.read_text(encoding="utf-8"))


def save_progress(progress: dict[str, str]) -> None:
    DNA_PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    DNA_PROGRESS.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")


def progress_failed(progress: dict[str, str], work_id: str) -> bool:
    return str(progress.get(work_id) or "").startswith("fail:")


def should_skip(
    work_id: str,
    *,
    force: bool,
    skip_failed: bool = False,
    progress: dict[str, str] | None = None,
) -> bool:
    if force:
        return False
    if skip_failed:
        state = progress if progress is not None else load_progress()
        if progress_failed(state, work_id):
            return True
    path = profile_path(work_id)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return int(data.get("version", 0)) == DNA_VERSION and data.get("prompt_version") == PROMPT_VERSION


def touch_heartbeat(
    *,
    work_id: str = "",
    note: str = "",
    profiles_ok: int | None = None,
) -> None:
    payload = {
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "work_id": work_id,
        "note": note,
        "profiles_ok": profiles_ok,
    }
    DNA_HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
    DNA_HEARTBEAT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_heartbeat() -> dict[str, Any] | None:
    if not DNA_HEARTBEAT.exists():
        return None
    try:
        return json.loads(DNA_HEARTBEAT.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_index() -> dict[str, Any] | None:
    return _cached_index()


@lru_cache(maxsize=1)
def _cached_index() -> dict[str, Any] | None:
    if not DNA_INDEX.exists():
        return None
    return json.loads(DNA_INDEX.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def index_by_work_id() -> dict[str, dict[str, Any]]:
    index = _cached_index()
    if not index:
        return {}
    return {
        str(item.get("work_id")): item
        for item in (index.get("items") or [])
        if item.get("work_id")
    }


def get_index_item(work_id: str) -> dict[str, Any] | None:
    return index_by_work_id().get(work_id)


def clear_index_cache() -> None:
    _cached_index.cache_clear()
    index_by_work_id.cache_clear()


def load_neighbors() -> dict[str, Any] | None:
    return _cached_neighbors()


@lru_cache(maxsize=1)
def _cached_neighbors() -> dict[str, Any] | None:
    if not DNA_NEIGHBORS.exists():
        return None
    return json.loads(DNA_NEIGHBORS.read_text(encoding="utf-8"))


def clear_neighbors_cache() -> None:
    _cached_neighbors.cache_clear()


def save_neighbors(payload: dict[str, Any]) -> Path:
    DNA_NEIGHBORS.parent.mkdir(parents=True, exist_ok=True)
    DNA_NEIGHBORS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    clear_neighbors_cache()
    return DNA_NEIGHBORS


def build_index() -> dict[str, Any]:
    DNA_DIR.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for path in sorted(DNA_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            profile = BookDNAProfile.model_validate(data)
        except (json.JSONDecodeError, ValueError):
            continue
        tropes = list(profile.tropes)
        if not tropes:
            tropes = derive_tropes_from_axes(profile.axes.model_dump(), None)
        items.append(
            {
                "work_id": profile.work_id,
                "title": profile.title,
                "authors": profile.authors,
                "axes": profile.axes.model_dump(),
                "themes": profile.themes,
                "tropes": tropes,
                "ai_tagline": profile.ai_tagline,
                "ai_summary": profile.ai_summary,
                "reader_badge": profile.reader_badge,
                "ai_overview": profile.ai_overview,
                "reviews_summary": profile.reviews_summary.model_dump(),
                "has_embedding": bool(profile.embedding),
                "sources": profile.sources.model_dump(),
                "updated_at": profile.updated_at,
            }
        )
    payload = {
        "version": DNA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "count": len(items),
        "items": items,
    }
    DNA_INDEX.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    clear_index_cache()
    return payload
