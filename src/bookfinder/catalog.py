from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz

from bookfinder.genre_filter import is_catalog_genre
from bookfinder.runtime_catalog import TOKEN_DB_NAME, normalize_search_text, word_stem
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


class TokenIndex:
    def __init__(self, db_path: Path) -> None:
        self._conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, check_same_thread=False)

    def lookup(self, token: str) -> tuple[int, ...]:
        rows = self._conn.execute(
            "SELECT rowid FROM token_hits WHERE token = ?",
            (token,),
        ).fetchall()
        return tuple(row[0] for row in rows)

    def close(self) -> None:
        self._conn.close()


@lru_cache
def _token_index() -> TokenIndex | None:
    path = DATA / TOKEN_DB_NAME
    if not path.exists():
        return None
    return TokenIndex(path)


@lru_cache
def load_works() -> list[dict]:
    for name in ("works_index.json", "expanded_works.json", "merged_works.json"):
        path = DATA / name
        if path.exists():
            works = json.loads(path.read_text(encoding="utf-8"))
            if name != "works_index.json":
                details_path = DATA / "works_details.json"
                for work in works:
                    if details_path.exists():
                        work.pop("description", None)
                        work.pop("description_source", None)
            return works
    return []


@lru_cache
def load_work_details() -> dict[str, dict]:
    path = DATA / "works_details.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache
def works_by_id() -> dict[str, dict]:
    return {work["id"]: work for work in load_works()}


def reload_works() -> list[dict]:
    index = _token_index()
    if index is not None:
        index.close()
    load_works.cache_clear()
    load_work_details.cache_clear()
    works_by_id.cache_clear()
    genre_counts.cache_clear()
    _search_cached.cache_clear()
    _token_index.cache_clear()
    _genre_indexes.cache_clear()
    return load_works()


@lru_cache
def genre_counts() -> list[dict]:
    path = DATA / "genres.json"
    if path.exists():
        items = json.loads(path.read_text(encoding="utf-8"))
        return [item for item in items if is_catalog_genre(item.get("name", ""), item.get("count", 0))]

    counts: dict[str, int] = {}
    works = load_works()
    for work in works:
        for genre in work.get("genres", []):
            if genre:
                counts[genre] = counts.get(genre, 0) + 1
    total = len(works) or 1
    return [
        {
            "name": name,
            "count": count,
            "weight": round(count / total, 4),
        }
        for name, count in sorted(counts.items(), key=lambda item: item[0].casefold())
        if is_catalog_genre(name, count)
    ]


def get_work(work_id: str) -> dict | None:
    work = works_by_id().get(work_id)
    if not work:
        return None
    item = {key: value for key, value in work.items() if key != "search_blurb"}
    details = load_work_details().get(work_id)
    if details:
        item.update(details)
    return item


def _genre_set(work: dict) -> set[str]:
    return {g.lower() for g in work.get("genres", []) if g}


def _normalize_text(text: str) -> str:
    return normalize_search_text(text)


def _normalize_query(query: str) -> str:
    return _normalize_text(query)


def _query_words(query: str) -> list[str]:
    normalized = _normalize_query(query)
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

    index = _token_index()
    if index is None:
        return None

    candidates: set[int] | None = None
    for word in words:
        hits: set[int] = set()
        for key in _token_keys(word):
            hits.update(index.lookup(key))
        if not hits:
            return set()
        candidates = hits if candidates is None else candidates & hits
    return candidates or set()


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
    for token in tokens:
        if _token_matches(word, token):
            return True
    return False


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

    q = _normalize_query(query)
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
        elif needle in hay or hay in needle:
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


def _resolve_genre_rowids(genre: str, index: dict[str, frozenset[int]]) -> frozenset[int]:
    key = genre.lower().strip()
    if not key:
        return frozenset()
    if key in index:
        return index[key]
    for name, rowids in index.items():
        if key in name or name in key:
            return rowids
    best_rowids: set[int] = set()
    best_score = 0.0
    for name, rowids in index.items():
        score = fuzz.partial_ratio(key, name) / 100
        if score >= 0.88 and score > best_score:
            best_score = score
            best_rowids = set(rowids)
    return frozenset(best_rowids)


def _genre_filter_rowids(selected: list[str], match: str) -> set[int] | None:
    if not selected:
        return None
    index = _genre_row_ids()
    sets = [set(_resolve_genre_rowids(genre, index)) for genre in selected]
    if match == "all":
        if not sets:
            return set()
        result = set.intersection(*sets)
    else:
        result = set().union(*sets)
    return result


def _iter_search_works(
    query: str,
    works: list[dict],
    *,
    genre_rowids: set[int] | None = None,
):
    if not query:
        if genre_rowids is not None:
            for rowid in genre_rowids:
                yield works[rowid]
            return
        for work in works:
            yield work
        return

    words = _query_words(query)
    candidates = _candidate_rowids(words)
    if candidates is not None:
        if genre_rowids is not None:
            candidates &= genre_rowids
        for rowid in candidates:
            yield works[rowid]
        return

    for rowid, work in enumerate(works):
        if genre_rowids is not None and rowid not in genre_rowids:
            continue
        yield work


def _search_works_impl(
    query: str = "",
    genres: list[str] | None = None,
    match: str = "any",
    limit: int = 100,
) -> dict:
    works = load_works()
    total = len(works) or 1
    selected = [g.strip() for g in (genres or []) if g and g.strip()]
    counts = {item["name"]: item["count"] for item in genre_counts()}
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
        items = [
            _slim_work(
                work,
                relevance=(work.get("aggregate_rating") or 0) / 100,
                text_score=1.0,
                genre_matches={},
                community_rating=community.get(work["id"]),
            )
            for work in works[:limit]
        ]
        return {
            "total": len(works),
            "query": query,
            "selected_genres": selected,
            "match_mode": match,
            "filters": [],
            "items": items,
        }

    scored: list[tuple[float, dict]] = []
    for work in _iter_search_works(query, works, genre_rowids=genre_rowids):
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
    items = all_matches[:limit]
    return {
        "total": len(all_matches),
        "query": query,
        "selected_genres": selected,
        "match_mode": match,
        "filters": _build_filter_stats(selected, counts, total, all_matches),
        "items": items,
    }


@lru_cache(maxsize=256)
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


@lru_cache
def _genre_indexes() -> tuple[dict[str, frozenset[int]], dict[str, frozenset[str]]]:
    by_rowid: dict[str, set[int]] = {}
    by_id: dict[str, set[str]] = {}
    for rowid, work in enumerate(load_works()):
        work_id = work["id"]
        for genre in work.get("genres", []):
            if not genre:
                continue
            key = genre.lower()
            by_rowid.setdefault(key, set()).add(rowid)
            by_id.setdefault(key, set()).add(work_id)
    return (
        {genre: frozenset(ids) for genre, ids in by_rowid.items()},
        {genre: frozenset(ids) for genre, ids in by_id.items()},
    )


def _genre_row_ids() -> dict[str, frozenset[int]]:
    return _genre_indexes()[0]


def _genre_work_ids() -> dict[str, frozenset[str]]:
    return _genre_indexes()[1]


@lru_cache
def _author_work_ids() -> dict[str, frozenset[str]]:
    index: dict[str, set[str]] = {}
    for work in load_works():
        work_id = work["id"]
        for author in work.get("authors", []):
            if author:
                index.setdefault(author.lower(), set()).add(work_id)
    return {author: frozenset(ids) for author, ids in index.items()}


def _similar_candidate_ids(work_id: str, base_genres: set[str], base_authors: set[str]) -> set[str]:
    candidates: set[str] = set()
    genre_index = _genre_work_ids()
    for genre in base_genres:
        candidates.update(genre_index.get(genre, ()))
    author_index = _author_work_ids()
    for author in base_authors:
        candidates.update(author_index.get(author, ()))
    candidates.discard(work_id)
    return candidates


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
    base = works_by_id().get(work_id)
    if not base:
        return []

    base_authors = {a.lower() for a in base.get("authors", []) if a}
    base_genres = _genre_set(base)
    base_title = _normalize_text(base.get("title", ""))
    by_id = works_by_id()

    candidate_ids = _similar_candidate_ids(work_id, base_genres, base_authors)
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
