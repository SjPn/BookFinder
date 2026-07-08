"""Runtime DNA profiles and recommendations."""

from __future__ import annotations

from functools import lru_cache

from bookfinder.book_dna import AXIS_HINTS_RU, AXIS_LABELS_RU, BookDNAProfile, derive_reader_badge
from bookfinder.catalog import LIST_ITEM_FIELDS, get_work
from bookfinder.dna_similarity import DNA_MODES, combined_similarity, match_axis_labels
from bookfinder.dna_store import load_index, load_neighbors, load_profile


@lru_cache
def dna_available() -> bool:
    index = load_index()
    return bool(index and index.get("count", 0) > 0)


def clear_dna_cache() -> None:
    dna_available.cache_clear()


def get_dna_profile(work_id: str) -> BookDNAProfile | None:
    return load_profile(work_id)


def get_dna_public(work_id: str) -> dict | None:
    profile = load_profile(work_id)
    if profile:
        return _public_payload(profile)

    index = load_index()
    if not index:
        return None
    for item in index.get("items") or []:
        if item.get("work_id") == work_id:
            axes = item.get("axes") or {}
            work = get_work(work_id) or {}
            reader_badge = str(item.get("reader_badge") or "").strip()
            if not reader_badge:
                reader_badge = derive_reader_badge(axes, work.get("genres") or [])
            return {
                "work_id": work_id,
                "title": item.get("title") or "",
                "authors": item.get("authors") or [],
                "axes": axes,
                "axis_labels": AXIS_LABELS_RU,
                "axis_hints": AXIS_HINTS_RU,
                "themes": item.get("themes") or [],
                "labels": {},
                "ai_tagline": item.get("ai_tagline") or "",
                "ai_summary": item.get("ai_summary") or "",
                "reader_badge": reader_badge,
                "ai_overview": item.get("ai_overview") or [],
                "reviews_summary": item.get("reviews_summary") or {},
                "sources": item.get("sources") or {},
                "modes": list(DNA_MODES),
                "has_full_profile": False,
            }
    return None


def _public_payload(profile: BookDNAProfile) -> dict:
    work = get_work(profile.work_id) or {}
    reader_badge = profile.reader_badge.strip()
    if not reader_badge:
        reader_badge = derive_reader_badge(profile.axes.model_dump(), work.get("genres") or [])
    return {
        "work_id": profile.work_id,
        "title": profile.title,
        "authors": profile.authors,
        "axes": profile.axes.model_dump(),
        "axis_labels": AXIS_LABELS_RU,
        "axis_hints": AXIS_HINTS_RU,
        "labels": profile.labels.model_dump(),
        "themes": profile.themes,
        "ai_tagline": profile.ai_tagline,
        "ai_summary": profile.ai_summary,
        "reader_badge": reader_badge,
        "ai_overview": profile.ai_overview,
        "reviews_summary": profile.reviews_summary.model_dump(),
        "sources": profile.sources.model_dump(),
        "modes": list(DNA_MODES),
        "has_full_profile": True,
        "updated_at": profile.updated_at,
    }


def _work_card(
    work_id: str,
    score: float,
    mode: str,
    *,
    match_axes: list[str] | None = None,
) -> dict | None:
    work = get_work(work_id)
    if not work:
        return None
    card = {key: work[key] for key in LIST_ITEM_FIELDS if key in work}
    card["dna_score"] = round(score, 4)
    card["match_mode"] = mode
    if match_axes:
        card["match_axes"] = match_axes
    return card


def similar_works_dna(work_id: str, *, mode: str = "ideas", limit: int = 12) -> list[dict]:
    if mode not in DNA_MODES:
        mode = "ideas"

    neighbors = load_neighbors()
    if neighbors:
        entry = (neighbors.get("items") or {}).get(work_id, {})
        rows = entry.get(mode) or []
        if rows:
            base = load_profile(work_id)
            result: list[dict] = []
            for row in rows[:limit]:
                candidate_id = str(row.get("work_id") or "")
                score = float(row.get("score") or 0.0)
                match_axes: list[str] | None = None
                if base:
                    candidate = load_profile(candidate_id)
                    if candidate:
                        match_axes = match_axis_labels(base, candidate, mode)
                card = _work_card(candidate_id, score, mode, match_axes=match_axes)
                if card:
                    result.append(card)
            if result:
                return result

    base = load_profile(work_id)
    if not base:
        return []

    index = load_index()
    if not index:
        return []

    base_work = get_work(work_id) or {}
    base_genres = {genre.casefold() for genre in base_work.get("genres") or [] if genre}

    scored: list[tuple[float, str]] = []
    for item in index.get("items") or []:
        candidate_id = str(item.get("work_id") or "")
        if not candidate_id or candidate_id == work_id:
            continue
        candidate = load_profile(candidate_id)
        if not candidate:
            continue
        candidate_work = get_work(candidate_id) or {}
        candidate_genres = {genre.casefold() for genre in candidate_work.get("genres") or [] if genre}
        score = combined_similarity(
            base,
            candidate,
            mode=mode,
            left_genres=base_genres,
            right_genres=candidate_genres,
        )
        if score > 0.05:
            scored.append((score, candidate_id))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    result = []
    for score, candidate_id in scored[:limit]:
        candidate = load_profile(candidate_id)
        match_axes = match_axis_labels(base, candidate, mode) if candidate else None
        card = _work_card(candidate_id, score, mode, match_axes=match_axes)
        if card:
            result.append(card)
    return result
