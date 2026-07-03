from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "processed"


@lru_cache
def load_works() -> list[dict]:
    for name in ("expanded_works.json", "merged_works.json"):
        path = DATA / name
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return []


def reload_works() -> list[dict]:
    load_works.cache_clear()
    return load_works()


def genre_counts() -> list[dict]:
    counts: dict[str, int] = {}
    for work in load_works():
        for genre in work.get("genres", []):
            if genre:
                counts[genre] = counts.get(genre, 0) + 1
    total = len(load_works()) or 1
    return [
        {
            "name": name,
            "count": count,
            "weight": round(count / total, 4),
        }
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _genre_set(work: dict) -> set[str]:
    return {g.lower() for g in work.get("genres", []) if g}


def _text_score(query: str, work: dict) -> float:
    if not query:
        return 1.0

    q = query.lower().strip()
    title = work.get("title", "").lower()
    authors = " ".join(work.get("authors", [])).lower()
    genres = " ".join(work.get("genres", [])).lower()
    if q in title:
        return 1.0
    if q in authors:
        return 0.95
    if q in genres:
        return 0.9
    if q in f"{title} {authors} {genres}":
        return 0.85

    return max(
        fuzz.partial_ratio(q, title) / 100,
        fuzz.partial_ratio(q, authors) / 100,
        fuzz.partial_ratio(q, genres) / 100,
    )


def _genre_match_score(filter_genre: str, work_genres: list[str]) -> float:
    needle = filter_genre.lower().strip()
    if not needle:
        return 0.0

    best = 0.0
    for genre in work_genres:
        hay = genre.lower()
        if hay == needle:
            best = max(best, 1.0)
        elif needle in hay or hay in needle:
            best = max(best, 0.88)
        else:
            best = max(best, fuzz.partial_ratio(needle, hay) / 100 * 0.72)
    return best


def search_works(
    query: str = "",
    genres: list[str] | None = None,
    match: str = "any",
    limit: int = 100,
) -> dict:
    works = load_works()
    total = len(works) or 1
    selected = [g.strip() for g in (genres or []) if g and g.strip()]
    counts = {item["name"]: item["count"] for item in genre_counts()}

    scored: list[tuple[float, dict]] = []
    for work in works:
        text_score = _text_score(query, work)
        if query and text_score < 0.42:
            continue

        genre_matches: dict[str, float] = {}
        if selected:
            for genre in selected:
                score = _genre_match_score(genre, work.get("genres", []))
                if score >= 0.5:
                    genre_matches[genre] = round(score, 3)

            if match == "all":
                if len(genre_matches) < len(selected):
                    continue
            elif not genre_matches:
                continue

        if selected:
            genre_relevance = sum(genre_matches.values()) / len(selected)
        else:
            genre_relevance = 1.0

        rating_norm = (work.get("aggregate_rating") or 0) / 100
        relevance = genre_relevance * 0.55 + text_score * 0.30 + rating_norm * 0.15

        item = dict(work)
        item["relevance"] = round(relevance * 100, 1)
        item["text_score"] = round(text_score, 3)
        item["genre_matches"] = genre_matches
        item["matched_genres"] = list(genre_matches.keys())
        scored.append((relevance, item))

    scored.sort(key=lambda pair: (-pair[0], -(pair[1].get("aggregate_rating") or 0)))
    all_matches = [item for _, item in scored]
    items = all_matches[:limit]

    filters: list[dict] = []
    for genre in selected:
        catalog_count = counts.get(genre, 0)
        if not catalog_count:
            for name, count in counts.items():
                if genre.lower() in name.lower() or name.lower() in genre.lower():
                    catalog_count = max(catalog_count, count)
        results_count = sum(1 for item in all_matches if genre in item.get("genre_matches", {}))
        result_share = results_count / len(all_matches) if all_matches else 0.0
        filters.append(
            {
                "name": genre,
                "catalog_count": catalog_count,
                "catalog_weight": round(catalog_count / total, 4),
                "results_count": results_count,
                "result_share": round(result_share, 4),
            }
        )

    return {
        "total": len(all_matches),
        "query": query,
        "selected_genres": selected,
        "match_mode": match,
        "filters": filters,
        "items": items,
    }


def similar_works(work_id: str, limit: int = 12) -> list[dict]:
    works = load_works()
    base = next((w for w in works if w["id"] == work_id), None)
    if not base:
        return []

    base_authors = {a.lower() for a in base.get("authors", [])}
    base_genres = _genre_set(base)
    base_title = base.get("title", "").lower()

    scored: list[tuple[float, dict]] = []
    for w in works:
        if w["id"] == work_id:
            continue
        genres = _genre_set(w)
        genre_score = len(base_genres & genres) / max(len(base_genres | genres), 1)
        author_score = 1.0 if base_authors & {a.lower() for a in w.get("authors", [])} else 0.0
        title_score = fuzz.token_sort_ratio(base_title, w.get("title", "").lower()) / 100
        score = genre_score * 0.45 + author_score * 0.35 + title_score * 0.2
        if score >= 0.25:
            scored.append((score, w))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [w for _, w in scored[:limit]]
