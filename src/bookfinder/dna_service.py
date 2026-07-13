"""Runtime DNA profiles and recommendations."""

from __future__ import annotations

import heapq
from dataclasses import dataclass
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
from bookfinder.dna_similarity import DNA_MODES, match_axis_labels_dicts, score_axis_theme_trope
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
    _similarity_rows.cache_clear()
    _similarity_by_id.cache_clear()


def warm_dna_caches() -> None:
    """Load DNA index into memory so the first book page is not cold."""
    if not dna_available():
        return
    _similarity_rows()


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


@dataclass(frozen=True)
class _SimRow:
    work_id: str
    axes: dict[str, int]
    themes: frozenset[str]
    tropes: frozenset[str]
    author_keys: frozenset[str]


@lru_cache(maxsize=1)
def _similarity_rows() -> tuple[_SimRow, ...]:
    rows: list[_SimRow] = []
    for work_id, item in index_by_work_id().items():
        axes = {str(k): int(v or 0) for k, v in (item.get("axes") or {}).items()}
        tropes = list(item.get("tropes") or [])
        if not tropes:
            tropes = derive_tropes_from_axes(axes, None)
        themes = frozenset(
            str(theme).strip().casefold()
            for theme in (item.get("themes") or [])
            if theme and str(theme).strip()
        )
        tropes_set = frozenset(str(trope).strip().casefold() for trope in tropes if trope)
        rows.append(
            _SimRow(
                work_id=work_id,
                axes=axes,
                themes=themes,
                tropes=tropes_set,
                author_keys=frozenset(_author_keys(item.get("authors") or [])),
            )
        )
    return tuple(rows)


@lru_cache(maxsize=1)
def _similarity_by_id() -> dict[str, _SimRow]:
    return {row.work_id: row for row in _similarity_rows()}


def _match_labels(base: _SimRow, other: _SimRow, mode: str) -> list[str]:
    labels = match_axis_labels_dicts(base.axes, other.axes, mode=mode)
    for key in sorted(base.tropes & other.tropes)[:2]:
        label = TROPE_LABELS_RU.get(key, key)
        if label not in labels:
            labels.append(label)
    return labels


def similar_works_dna(work_id: str, *, mode: str = "ideas", limit: int = 12) -> list[dict]:
    """Recommend by DNA axes/themes/tropes from dna_index (works on Render without dna/*.json)."""
    if mode not in DNA_MODES:
        mode = "ideas"

    rows = _similarity_rows()
    if not rows:
        return []

    by_id = _similarity_by_id()
    base = by_id.get(work_id)
    if base is None:
        item = get_index_item(work_id)
        if not item:
            profile = load_profile(work_id)
            if not profile:
                return []
            item = {
                "work_id": work_id,
                "authors": profile.authors,
                "axes": profile.axes.model_dump(),
                "themes": profile.themes,
                "tropes": profile.tropes,
            }
        tropes = list(item.get("tropes") or [])
        if not tropes:
            tropes = derive_tropes_from_axes(item.get("axes") or {}, None)
        base = _SimRow(
            work_id=work_id,
            axes={str(k): int(v or 0) for k, v in (item.get("axes") or {}).items()},
            themes=frozenset(
                str(theme).strip().casefold()
                for theme in (item.get("themes") or [])
                if theme and str(theme).strip()
            ),
            tropes=frozenset(str(trope).strip().casefold() for trope in tropes if trope),
            author_keys=frozenset(_author_keys(item.get("authors") or [])),
        )

    other_heap: list[tuple[float, str]] = []
    same_heap: list[tuple[float, str]] = []
    keep = max(limit * 3, 24)

    for row in rows:
        if row.work_id == work_id:
            continue
        score = score_axis_theme_trope(
            base.axes,
            row.axes,
            base.themes,
            row.themes,
            base.tropes,
            row.tropes,
            mode=mode,
        )
        if score <= 0.05:
            continue
        if base.author_keys and row.author_keys and (base.author_keys & row.author_keys):
            entry = (score * 0.2, row.work_id)
            if len(same_heap) < keep:
                heapq.heappush(same_heap, entry)
            else:
                heapq.heappushpop(same_heap, entry)
        else:
            entry = (score, row.work_id)
            if len(other_heap) < keep:
                heapq.heappush(other_heap, entry)
            else:
                heapq.heappushpop(other_heap, entry)

    ranked = sorted(other_heap, key=lambda pair: pair[0], reverse=True)
    if len(ranked) < limit:
        ranked.extend(sorted(same_heap, key=lambda pair: pair[0], reverse=True))

    result: list[dict] = []
    seen: set[str] = set()
    for score, candidate_id in ranked:
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        other = by_id.get(candidate_id)
        labels = _match_labels(base, other, mode) if other else []
        card = _work_card(candidate_id, score, mode, match_axes=labels)
        if card:
            result.append(card)
        if len(result) >= limit:
            break
    return result
