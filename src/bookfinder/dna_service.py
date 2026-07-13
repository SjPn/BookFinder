"""Runtime DNA profiles and recommendations."""

from __future__ import annotations

from functools import lru_cache

from bookfinder.book_dna import (
    AXIS_HINTS_RU,
    AXIS_LABELS_RU,
    TROPE_LABELS_RU,
    BookDNAProfile,
    derive_reader_badge,
    derive_tropes_from_axes,
    trope_labels,
)
from bookfinder.catalog import LIST_ITEM_FIELDS, get_work
from bookfinder.dna_similarity import DNA_MODES, index_similarity, match_axis_labels_dicts
from bookfinder.dna_store import get_index_item, index_by_work_id, load_index, load_profile
from bookfinder.normalize import author_surname, normalize_authors


@lru_cache
def dna_available() -> bool:
    index = load_index()
    return bool(index and index.get("count", 0) > 0)


def clear_dna_cache() -> None:
    from bookfinder.dna_store import clear_index_cache, clear_neighbors_cache

    dna_available.cache_clear()
    clear_index_cache()
    clear_neighbors_cache()


def get_dna_profile(work_id: str) -> BookDNAProfile | None:
    return load_profile(work_id)


def get_dna_public(work_id: str) -> dict | None:
    profile = load_profile(work_id)
    if profile:
        return _public_payload(profile)

    item = get_index_item(work_id)
    if not item:
        return None

    axes = item.get("axes") or {}
    work = get_work(work_id) or {}
    tropes = list(item.get("tropes") or [])
    if not tropes:
        tropes = derive_tropes_from_axes(axes, work.get("genres") or [])
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
        "tropes": tropes,
        "trope_labels": trope_labels(tropes),
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


def _public_payload(profile: BookDNAProfile) -> dict:
    work = get_work(profile.work_id) or {}
    tropes = list(profile.tropes)
    if not tropes:
        tropes = derive_tropes_from_axes(profile.axes.model_dump(), work.get("genres") or [])
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
        "tropes": tropes,
        "trope_labels": trope_labels(tropes),
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


def _author_keys(authors: list[str] | None) -> set[str]:
    keys: set[str] = set()
    for author in normalize_authors(list(authors or [])):
        surname = author_surname(author)
        if surname:
            keys.add(surname)
        for token in author.split():
            if len(token) >= 5:
                keys.add(token)
    return keys


def _same_author(left: list[str] | None, right: list[str] | None) -> bool:
    a = _author_keys(left)
    b = _author_keys(right)
    return bool(a and b and (a & b))


def _enriched_item(item: dict) -> dict:
    """Ensure tropes exist for scoring/UI even on old index rows."""
    tropes = list(item.get("tropes") or [])
    if tropes:
        return item
    derived = derive_tropes_from_axes(item.get("axes") or {}, None)
    if not derived:
        return item
    enriched = dict(item)
    enriched["tropes"] = derived
    return enriched


def similar_works_dna(work_id: str, *, mode: str = "ideas", limit: int = 12) -> list[dict]:
    """Recommend by DNA axes/themes/tropes from dna_index (works on Render without dna/*.json)."""
    if mode not in DNA_MODES:
        mode = "ideas"

    base_item = get_index_item(work_id)
    if not base_item:
        profile = load_profile(work_id)
        if not profile:
            return []
        base_item = {
            "work_id": work_id,
            "title": profile.title,
            "authors": profile.authors,
            "axes": profile.axes.model_dump(),
            "themes": profile.themes,
            "tropes": profile.tropes,
            "reviews_summary": profile.reviews_summary.model_dump(),
        }
    base_item = _enriched_item(base_item)

    base_authors = list(base_item.get("authors") or [])
    index_map = index_by_work_id()

    other: list[tuple[float, str, list[str]]] = []
    same_author: list[tuple[float, str, list[str]]] = []

    for candidate_id, raw_item in index_map.items():
        if candidate_id == work_id:
            continue
        item = _enriched_item(raw_item)
        score = index_similarity(base_item, item, mode=mode)
        if score <= 0.05:
            continue
        labels = match_axis_labels_dicts(
            base_item.get("axes") or {},
            item.get("axes") or {},
            mode=mode,
        )
        shared_tropes = sorted(set(base_item.get("tropes") or []) & set(item.get("tropes") or []))
        for key in shared_tropes[:2]:
            label = TROPE_LABELS_RU.get(key, key)
            if label not in labels:
                labels.append(label)
        row = (score, candidate_id, labels)
        if _same_author(base_authors, item.get("authors") or []):
            same_author.append((score * 0.2, candidate_id, labels))
        else:
            other.append(row)

    other.sort(key=lambda pair: pair[0], reverse=True)
    chosen = other[:limit]
    if len(chosen) < limit:
        same_author.sort(key=lambda pair: pair[0], reverse=True)
        seen = {row[1] for row in chosen}
        for row in same_author:
            if len(chosen) >= limit:
                break
            if row[1] not in seen:
                chosen.append(row)
                seen.add(row[1])

    result = []
    for score, candidate_id, labels in chosen:
        card = _work_card(candidate_id, score, mode, match_axes=labels)
        if card:
            result.append(card)
    return result
