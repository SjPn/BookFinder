"""Persist book DNA profiles on disk."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from bookfinder.book_dna import BookDNAProfile, DNA_VERSION, PROMPT_VERSION

ROOT = Path(__file__).resolve().parents[2]
DNA_DIR = ROOT / "data" / "processed" / "dna"
DNA_INDEX = ROOT / "data" / "processed" / "dna_index.json"
DNA_PROGRESS = ROOT / "data" / "processed" / "dna_progress.json"
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


def should_skip(work_id: str, *, force: bool) -> bool:
    if force:
        return False
    path = profile_path(work_id)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return int(data.get("version", 0)) == DNA_VERSION and data.get("prompt_version") == PROMPT_VERSION


def build_index() -> dict[str, Any]:
    DNA_DIR.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for path in sorted(DNA_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            profile = BookDNAProfile.model_validate(data)
        except (json.JSONDecodeError, ValueError):
            continue
        items.append(
            {
                "work_id": profile.work_id,
                "title": profile.title,
                "authors": profile.authors,
                "axes": profile.axes.model_dump(),
                "themes": profile.themes,
                "ai_tagline": profile.ai_tagline,
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
    return payload
