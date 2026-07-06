from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz

from bookfinder.catalog_db import CatalogStore
from bookfinder.runtime_catalog import normalize_search_text, word_stem
from bookfinder.user_ratings import community_stats_index

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "processed"
_TOKEN_SPLIT = re.compile(r"[\s+.,;:!?\-\"«»()\[\]/]+")

LIST_ITEM_FIELDS = (
    "id",
    "title",
    "authors",
    "genres",
    "year",
    "aggregate_rating",
    "source_origin",
    "download_url",
    "fb2_local",
    "fantlab",
    "livelib",
    "fantasy_worlds",
    "kubikus",
    "bookmix",
    "loveread",
)

_store = CatalogStore(DATA)


def _using_db() -> bool:
    return _store.available()


@lru_cache
def _load_works_json() -> list[dict]:
    """Legacy fallback when catalog.db is missing (local dev only)."""
    for name in ("works_index.json", "expanded_works.json", "merged_works.json"):
        path = DATA / name
        if path.exists():
            works = json.loads(path.read_text(encoding="utf-8"))
            if name != "works_index.json":
                details_path = DATA / "works_details.json"
                if details_path.exists():
                    details = json.loads(details_path.read_text(encoding="utf-8"))
                    for work in works:
                        work.update(details.get(work["id"], {}))
            return works
    return []


def load_works() -> list[dict]:
    if _using_db():
        raise RuntimeError("load_works() loads entire catalog into RAM; use catalog.db queries instead")
    return _load_works_json()


def works_count() -> int:
    if _using_db():
        return _store.count_works()
    return len(_load_works_json())


def works_by_id() -> dict[str, dict]:
    if _using_db():
        raise RuntimeError("works_by_id() loads entire catalog into RAM; use get_work() instead")
    return {work["id"]: work for work in _load_works_json()}


def reload_works() -> int:
    _store.close_thread()
    _load_works_json.cache_clear()
    _load_work_details_json.cache_clear()
    genre_counts.cache_clear()
    _search_cached.cache_clear()
    _genre_name_cache.cache_clear()
    return works_count()


@lru_cache
def _load_work_details_json() -> dict[str, dict]:
    path = DATA / "works_details.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache
def genre_counts() -> list[dict]:
    if _using_db():
        return _store.list_genres()
    path = DATA / "genres.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    total = len(_load_works_json()) or 1
    counts: dict[str, int] = {}
    for work in _load_works_json():
        for genre in work.get("genres", []):
            if genre:
                counts[genre] = counts.get(genre, 0) + 1
    return [
        {"name": name, "count": count, "weight": round(count / total, 4)}
        for name, count in sorted(counts.items(), key=lambda item: item[0].casefold())
    ]


def get_work(work_id: str) -> dict | None:
    if _using_db():
        return _store.get_work(work_id)
    work = works_by_id().get(work_id)
    if not work:
        return None
    item = {key: value for key, value in work.items() if key != "search_blurb"}
    item.update(_load_work_details_json().get(work_id, {}))
    return item


def _genre_set(work: dict) -> set[str]:
    return {g.lower() for g in work.get("genres", []) if g}


def _normalize_text(text: str) -> str:
    return normalize_search_text(text)


def _query_words(query: str) -> list[str]:
    normalized = _normalize_text(query)
    if not normalized:
        return []
    return [word for word in _TOKEN_SPLIT.split(normalized) if len(word) >= 2]


def _word_stem(word: str) -> str:
    return word_stem(word)


def _token_keys(word: str) -> set[str]:
    keys = {word}
    stem = _word_stem(word)
    if stem and len(stem) >= 4:
        keys.add(stem)
    return keys


def _candidate_rowids(words: list[str]) -> set[int] | None:
    if not words:
        return None
    if not _using_db():
        return None

    candidates: set[int] | None = None
    for word in words:
        hits: set[int] = set()
        for key in _token_keys(word):
            hits.update(_store.lookup_tokens(key))
        if not hits:
            return set()
        candidates = hits if candidates is None else candidates & hits
    return candidates or set()


@lru_cache
def _genre_name_cache() -> list[str]:
    if _using_db():
        return _store.genre_names()
    return [item["name"] for item in genre_counts()]


def _resolve_genre_rowids(genre: str) -> frozenset[int]:
    key = genre.lower().strip()
    if not key:
        return frozenset()
    if _using_db():
        exact = _store.rowids_for_genre_lower(key)
        if exact:
            return exact
        partial = _store.rowids_for_genre_substring(key)
        if partial:
            return partial
        best_name = ""
        best_score = 0.0
        for name in _genre_name_cache():
            score = fuzz.partial_ratio(key, name.lower()) / 100
            if score >= 0.88 and score > best_score:
                best_score = score
                best_name = name
        if best_name:
            return _store.rowids_for_genre_lower(best_name.casefold())
        return frozenset()

    index = _legacy_genre_row_ids()
    if key in index:
        return index[key]
    for name, rowids in index.items():
        if key in name or name in key:
            return rowids
    return frozenset()


@lru_cache
def _legacy_genre_row_ids() -> dict[str, frozenset[int]]:
    index: dict[str, set[int]] = {}
    for rowid, work in enumerate(_load_works_json()):
        for genre in work.get("genres", []):
            if genre:
                index.setdefault(genre.lower(), set()).add(rowid)
    return {genre: frozenset(ids) for genre, ids in index.items()}


def _genre_filter_rowids(selected: list[str], match: str) -> set[int] | None:
    if not selected:
        return None
    sets = [set(_resolve_genre_rowids(genre)) for genre in selected]
    if match == "all":
        if not sets:
            return set()
        result = set.intersection(*sets)
    else:
        result = set().union(*sets)
    return result


def _tokenize(text: str) -> tuple[str, ...]:
    return tuple(token for token in _TOKEN_SPLIT.split(_normalize_text(text)) if len(token) >= 2)


def _token_matches(word: str, token: str) -> bool:
    if token == word:
        return True
    if len(word) <= 3:
        return False
    stem = _word_stem(word)
    token_stem = _word_stem(token)
    if stem and token_stem and stem == token_stem:
        return True
    if stem and len(stem) >= 4 and token.startswith(stem):
        return True
    return False


def _stem_in_tokens(word: str, tokens: tuple[str, ...]) -> bool:
    return any(_token_matches(word, token) for token in tokens)


def _work_tokens(work: dict) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], str, str, str, str]:
    title = _normalize_text(work.get("title", ""))
    authors = _normalize_text(" ".join(work.get("authors", [])))
    genres = _normalize_text(" ".join(work.get("genres", [])))
    blurb = _normalize_text(work.get("search_blurb", ""))
    full = f"{title} {authors} {genres} {blurb}"
    return (
        _tokenize(title),
        _tokenize(authors),
        _tokenize(full),
        title,
        authors,
        genres,
        full,
    )


def _text_score(query: str, work: dict, cached: tuple | None = None) -> float:
    if not query:
        return 1.0

    q = _normalize_text(query)
    if not q:
        return 1.0

    if cached is None:
        title_tokens, author_tokens, full_tokens, title, authors, genres, full = _work_tokens(work)
    else:
        title_tokens, author_tokens, full_tokens, title, authors, genres, full = cached

    words = _query_words(q)

    if len(words) >= 2:
        if q in title:
            return 1.0
        if all(_stem_in_tokens(word, title_tokens) for word in words):
            return 0.98
        if all(_stem_in_tokens(word, title_tokens + author_tokens) for word in words):
            return 0.93
        if all(_stem_in_tokens(word, full_tokens) for word in words):
            return 0.78
        matched = sum(1 for word in words if _stem_in_tokens(word, full_tokens))
        if matched >= len(words) - 1 and matched >= 2:
            return 0.65 + 0.08 * matched
        title_ratio = fuzz.token_sort_ratio(q, title) / 100
        if title_ratio >= 0.72:
            return title_ratio * 0.88
        return 0.0

    word = words[0] if words else q
    if q in title:
        return 1.0
    if _stem_in_tokens(word, title_tokens):
        return 0.92
    if q in authors or _stem_in_tokens(word, author_tokens):
        return 0.9
    if q in genres:
        return 0.85
    if q in full or _stem_in_tokens(word, full_tokens):
        return 0.82

    title_ratio = fuzz.ratio(q, title) / 100
    if title_ratio >= 0.72:
        return title_ratio * 0.9

    author_ratio = fuzz.ratio(q, authors) / 100 if authors else 0.0
    if author_ratio >= 0.78:
        return author_ratio * 0.85

    return 0.0


def _genre_match_score(filter_genre: str, work_genres: list[str]) -> float:
    needle = filter_genre.lower().strip()
    if not needle:
        return 0.0

    best = 0.0
    for genre in work_genres:
        hay = genre.lower()
        if hay == needle:
            return 1.0
        if needle in hay or hay in needle:
            best = max(best, 0.88)
        else:
            best = max(best, fuzz.partial_ratio(needle, hay) / 100 * 0.72)
    return best


def _slim_work(
    work: dict,
    *,
    relevance: float,
    text_score: float,
    genre_matches: dict[str, float],
    community_rating: dict | None,
) -> dict:
    item = {key: work[key] for key in LIST_ITEM_FIELDS if key in work}
    item["relevance"] = round(relevance * 100, 1)
    item["text_score"] = round(text_score, 3)
    item["genre_matches"] = genre_matches
    item["matched_genres"] = list(genre_matches.keys())
    item["community_rating"] = community_rating
    return item


def _build_filter_stats(
    selected: list[str],
    counts: dict[str, int],
    total: int,
    all_matches: list[dict],
) -> list[dict]:
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
    return filters


def _iter_search_rowids(query: str, genre_rowids: set[int] | None) -> list[int]:
    if not query:
        if genre_rowids is not None:
            return sorted(genre_rowids)
        if _using_db():
            return []
        return list(range(len(_load_works_json())))

    words = _query_words(query)
    candidates = _candidate_rowids(words)
    if candidates is not None:
        if genre_rowids is not None:
            candidates &= genre_rowids
        return sorted(candidates)

    if _using_db():
        return []

    rowids: list[int] = []
    for rowid in range(len(_load_works_json())):
        if genre_rowids is not None and rowid not in genre_rowids:
            continue
        rowids.append(rowid)
    return rowids


def _works_for_rowids(rowids: list[int]) -> list[dict]:
    if not rowids:
        return []
    if _using_db():
        return _store.get_works_by_rowids(rowids)
    works = _load_works_json()
    return [works[rowid] for rowid in rowids if 0 <= rowid < len(works)]


def _search_works_impl(
    query: str = "",
    genres: list[str] | None = None,
    match: str = "any",
    limit: int = 100,
) -> dict:
    total = works_count() or 1
    selected = [g.strip() for g in (genres or []) if g and g.strip()]
    counts = _store.genre_catalog_counts() if _using_db() else {item["name"]: item["count"] for item in genre_counts()}
    community = community_stats_index()
    genre_rowids = _genre_filter_rowids(selected, match)

    if genre_rowids is not None and not genre_rowids:
        return {
            "total": 0,
            "query": query,
            "selected_genres": selected,
            "match_mode": match,
            "filters": _build_filter_stats(selected, counts, total, []),
            "items": [],
        }

    if not query and not selected:
        works = _store.top_works(limit) if _using_db() else _load_works_json()[:limit]
        items = [
            _slim_work(
                work,
                relevance=(work.get("aggregate_rating") or 0) / 100,
                text_score=1.0,
                genre_matches={},
                community_rating=community.get(work["id"]),
            )
            for work in works
        ]
        return {
            "total": works_count(),
            "query": query,
            "selected_genres": selected,
            "match_mode": match,
            "filters": [],
            "items": items,
        }

    if not query and genre_rowids is not None and _using_db():
        rowids = sorted(genre_rowids)
    else:
        rowids = _iter_search_rowids(query, genre_rowids)

    scored: list[tuple[float, dict]] = []
    for work in _works_for_rowids(rowids):
        token_cache = _work_tokens(work) if query else None
        text_score = _text_score(query, work, token_cache)
        if query and text_score < 0.55:
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

        genre_relevance = sum(genre_matches.values()) / len(selected) if selected else 1.0
        rating_norm = (work.get("aggregate_rating") or 0) / 100
        if query:
            relevance = text_score * 0.78 + genre_relevance * 0.12 + rating_norm * 0.10
        else:
            relevance = genre_relevance * 0.55 + text_score * 0.30 + rating_norm * 0.15

        scored.append(
            (
                relevance,
                _slim_work(
                    work,
                    relevance=relevance,
                    text_score=text_score,
                    genre_matches=genre_matches,
                    community_rating=community.get(work["id"]),
                ),
            )
        )

    if query:
        scored.sort(
            key=lambda pair: (
                -pair[1].get("text_score", 0),
                -pair[0],
                -(pair[1].get("aggregate_rating") or 0),
            ),
        )
    else:
        scored.sort(key=lambda pair: (-pair[0], -(pair[1].get("aggregate_rating") or 0)))

    all_matches = [item for _, item in scored]
    return {
        "total": len(all_matches),
        "query": query,
        "selected_genres": selected,
        "match_mode": match,
        "filters": _build_filter_stats(selected, counts, total, all_matches),
        "items": all_matches[:limit],
    }


@lru_cache(maxsize=512)
def _search_cached(query: str, genres: tuple[str, ...], match: str, limit: int) -> str:
    return json.dumps(
        _search_works_impl(query=query, genres=list(genres), match=match, limit=limit),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def search_works(
    query: str = "",
    genres: list[str] | None = None,
    match: str = "any",
    limit: int = 100,
) -> dict:
    genres_key = tuple(sorted(g.strip() for g in (genres or []) if g and g.strip()))
    payload = _search_cached(query.strip(), genres_key, match, limit)
    return json.loads(payload)


def _score_similar_work(
    work: dict,
    base_genres: set[str],
    base_authors: set[str],
    base_title: str,
    *,
    with_title: bool = True,
) -> float:
    genres = _genre_set(work)
    genre_score = len(base_genres & genres) / max(len(base_genres | genres), 1)
    author_score = 1.0 if base_authors & {a.lower() for a in work.get("authors", [])} else 0.0
    if not with_title:
        return genre_score * 0.45 + author_score * 0.35
    title = _normalize_text(work.get("title", ""))
    title_score = fuzz.token_sort_ratio(base_title, title) / 100
    return genre_score * 0.45 + author_score * 0.35 + title_score * 0.2


def similar_works(work_id: str, limit: int = 12) -> list[dict]:
    base = get_work(work_id)
    if not base:
        return []

    base_authors = {a.lower() for a in base.get("authors", []) if a}
    base_genres = _genre_set(base)
    base_title = _normalize_text(base.get("title", ""))

    if _using_db():
        candidate_ids = _store.similar_candidate_ids(work_id, base_genres, base_authors)
        candidates = _store.get_works_by_ids(candidate_ids)
        by_id = {work["id"]: work for work in candidates}
    else:
        by_id = works_by_id()
        candidate_ids = set()
        for genre in base_genres:
            for wid in _legacy_genre_work_ids().get(genre, ()):
                candidate_ids.add(wid)
        candidate_ids.discard(work_id)

    if not candidate_ids:
        return []

    if len(candidate_ids) > 400:
        prelim: list[tuple[float, str]] = []
        for candidate_id in candidate_ids:
            work = by_id.get(candidate_id)
            if not work:
                continue
            partial = _score_similar_work(work, base_genres, base_authors, base_title, with_title=False)
            if partial >= 0.1:
                prelim.append((partial, candidate_id))
        prelim.sort(key=lambda pair: pair[0], reverse=True)
        candidate_ids = {candidate_id for _, candidate_id in prelim[:200]}

    scored: list[tuple[float, dict]] = []
    for candidate_id in candidate_ids:
        work = by_id.get(candidate_id)
        if not work:
            continue
        score = _score_similar_work(work, base_genres, base_authors, base_title)
        if score >= 0.25:
            scored.append((score, {key: work[key] for key in LIST_ITEM_FIELDS if key in work}))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:limit]]


@lru_cache
def _legacy_genre_work_ids() -> dict[str, frozenset[str]]:
    index: dict[str, set[str]] = {}
    for work in _load_works_json():
        work_id = work["id"]
        for genre in work.get("genres", []):
            if genre:
                index.setdefault(genre.lower(), set()).add(work_id)
    return {genre: frozenset(ids) for genre, ids in index.items()}
