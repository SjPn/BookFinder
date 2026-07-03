"""Build merged catalog from FantLab + LiveLib + Fantasy-Worlds caches."""

from __future__ import annotations

import json
import math
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rapidfuzz import fuzz

from bookfinder.models import BookRecord
from bookfinder.normalize import normalize_authors, normalize_title
from bookfinder.matcher import MATCH_THRESHOLD, find_best_match
from bookfinder.parsers import fantasy_worlds as fw
from bookfinder.parsers import livelib

DATA = ROOT / "data"
RAW = DATA / "raw"
OUT = DATA / "processed"
SEARCH_DIR = RAW / "livelib_search"
FW_SEARCH_DIR = RAW / "fw_search"
FW_BOOKS_DIR = RAW / "fw_books"


def load_books(path: Path) -> list[BookRecord]:
    if not path.exists():
        return []
    books: list[BookRecord] = []
    for item in json.loads(path.read_text(encoding="utf-8")):
        item = dict(item)
        item.pop("normalized_score", None)
        book = BookRecord(**item)
        book.normalized_title = normalize_title(book.title)
        book.normalized_authors = normalize_authors(book.authors)
        books.append(book)
    return books


def _fantlab_for_file(path: Path, fantlab_books: list[BookRecord], by_id: dict[str, BookRecord]) -> BookRecord | None:
    prefix = path.stem.split("_", 1)[0]
    if prefix in by_id:
        return by_id[prefix]
    parts = path.stem.split("_", 1)
    if len(parts) > 1:
        hint = parts[1].replace("_", " ")
        best = max(
            fantlab_books,
            key=lambda fl: fuzz.token_sort_ratio(normalize_title(fl.title), normalize_title(hint)),
        )
        if fuzz.token_sort_ratio(normalize_title(best.title), normalize_title(hint)) >= 85:
            return best
    return None


def load_search_map(fantlab_books: list[BookRecord]) -> dict[str, list[BookRecord]]:
    by_id = {b.external_id: b for b in fantlab_books}
    mapping: dict[str, list[BookRecord]] = {}
    if not SEARCH_DIR.exists():
        return mapping
    for path in SEARCH_DIR.glob("*.html"):
        html = path.read_text(encoding="utf-8", errors="ignore")
        if "DDoS-Guard" in html or len(html) < 3000:
            continue
        fantlab_book = _fantlab_for_file(path, fantlab_books, by_id)
        if fantlab_book is None:
            continue
        candidates = livelib.parse_search_page(html, fantlab_book.title, fantlab_book.authors)
        for c in candidates:
            c.normalized_title = normalize_title(c.title)
            c.normalized_authors = normalize_authors(c.authors)
        if candidates:
            mapping.setdefault(fantlab_book.external_id, []).extend(candidates)
    return mapping


def load_fw_links() -> dict[str, dict]:
    path = OUT / "fw_download_links.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_fw_map(fantlab_books: list[BookRecord]) -> dict[str, BookRecord]:
    by_fantlab_id = {b.external_id: b for b in fantlab_books}
    mapping: dict[str, BookRecord] = {}
    links = load_fw_links()

    for fantlab_id, link in links.items():
        fw_id = link.get("fw_id")
        if not fw_id or fantlab_id in mapping:
            continue
        mapping[fantlab_id] = BookRecord(
            source="fantasy_worlds",
            external_id=str(fw_id),
            title=link.get("title") or by_fantlab_id[fantlab_id].title,
            authors=by_fantlab_id[fantlab_id].authors if fantlab_id in by_fantlab_id else [],
            url=link.get("url") or fw.book_url(fw_id),
            normalized_title=normalize_title(link.get("title") or ""),
            normalized_authors=normalize_authors(by_fantlab_id[fantlab_id].authors if fantlab_id in by_fantlab_id else []),
        )

    if FW_BOOKS_DIR.exists():
        for path in FW_BOOKS_DIR.glob("*.html"):
            html = path.read_text(encoding="utf-8", errors="ignore")
            fantlab_id = fw.extract_fantlab_id(html)
            if not fantlab_id or fantlab_id not in by_fantlab_id:
                continue
            record = fw.parse_book_page(html)
            if record:
                mapping[fantlab_id] = record

    if not FW_SEARCH_DIR.exists():
        return mapping

    for path in FW_SEARCH_DIR.glob("*.json"):
        fantlab_id = path.stem
        if fantlab_id in mapping:
            continue
        fl = by_fantlab_id.get(fantlab_id)
        if fl is None:
            continue
        try:
            candidates = fw.parse_search_json(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for candidate in candidates:
            candidate.normalized_title = normalize_title(candidate.title)
            candidate.normalized_authors = normalize_authors(candidate.authors)
        result = find_best_match(fl, candidates, MATCH_THRESHOLD) if candidates else None
        if result:
            mapping[fantlab_id] = result.livelib  # type: ignore[assignment]

    for fantlab_id, link in links.items():
        if fantlab_id in mapping or not link.get("fw_id"):
            continue
        fw_id = str(link["fw_id"])
        mapping[fantlab_id] = BookRecord(
            source="fantasy_worlds",
            external_id=fw_id,
            title=link.get("title") or "",
            authors=[],
            url=link.get("url") or fw.book_url(fw_id),
        )

    return mapping


def aggregate_rating(
    fl: BookRecord,
    ll: BookRecord | None,
    fw_book: BookRecord | None = None,
) -> float | None:
    parts: list[tuple[float, float]] = []
    if fl.rating is not None:
        parts.append((fl.rating / fl.rating_max * 100, math.log1p(fl.vote_count or 1)))
    if ll and ll.rating is not None:
        parts.append((ll.rating / ll.rating_max * 100, math.log1p(ll.vote_count or 1)))
    if fw_book and fw_book.rating is not None:
        parts.append((fw_book.rating / fw_book.rating_max * 100, math.log1p(fw_book.vote_count or 1)))
    if not parts:
        return None
    total_w = sum(w for _, w in parts)
    return sum(s * w for s, w in parts) / total_w


def main() -> None:
    fantlab = load_books(OUT / "fantlab_books.json")
    livelib_top = load_books(OUT / "livelib_top.json")
    search_map = load_search_map(fantlab)
    fw_map = load_fw_map(fantlab)

    matched_count = 0
    matched_with_cache = 0
    cache_total = len(search_map)
    fw_matched = 0
    works: list[dict] = []

    for fl in fantlab:
        candidates = list(search_map.get(fl.external_id, []))
        for book in livelib_top:
            if find_best_match(fl, [book], threshold=0.65):
                candidates.append(book)

        ll: BookRecord | None = None
        score = 0.0
        result = find_best_match(fl, candidates, MATCH_THRESHOLD) if candidates else None
        if result:
            ll = result.livelib
            score = result.score
            matched_count += 1
            if fl.external_id in search_map:
                matched_with_cache += 1

        fw_book = fw_map.get(fl.external_id)
        if fw_book:
            fw_matched += 1

        agg = aggregate_rating(fl, ll, fw_book)
        if agg is None or agg < 60:
            continue

        genres = list(fl.genres)
        if fl.work_type and fl.work_type not in genres:
            genres.insert(0, fl.work_type)
        for tag in fw_book.genres if fw_book else []:
            if tag not in genres:
                genres.append(tag)

        entry: dict = {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"fl:{fl.external_id}")),
            "title": fl.title,
            "authors": fl.authors,
            "genres": genres,
            "year": fl.year,
            "aggregate_rating": round(agg, 2),
            "fantlab": {
                "id": fl.external_id,
                "rating": fl.rating,
                "votes": fl.vote_count,
                "url": fl.url,
            },
            "match_score": round(score, 3) if ll else None,
        }
        if ll:
            entry["livelib"] = {"id": ll.external_id, "rating": ll.rating, "url": ll.url}
        if fw_book:
            entry["fantasy_worlds"] = {
                "id": fw_book.external_id,
                "rating": fw_book.rating,
                "votes": fw_book.vote_count,
                "url": fw_book.url,
                "download_url": fw.download_url(fw_book.external_id),
            }
            entry["download_url"] = fw.download_url(fw_book.external_id)
        works.append(entry)

    works.sort(key=lambda w: w["aggregate_rating"], reverse=True)

    cache_match_rate = (matched_with_cache / cache_total * 100) if cache_total else 0.0
    overall_match_rate = matched_count / len(fantlab) * 100 if fantlab else 0.0

    summary = {
        "fantlab_total": len(fantlab),
        "search_cached": cache_total,
        "matched_total": matched_count,
        "matched_with_search_cache": matched_with_cache,
        "match_rate_on_cached_percent": round(cache_match_rate, 2),
        "match_rate_overall_percent": round(overall_match_rate, 2),
        "works_above_60": len(works),
        "fw_matched": fw_matched,
        "fw_search_cached": len(list(FW_SEARCH_DIR.glob("*.json"))) if FW_SEARCH_DIR.exists() else 0,
        "threshold": MATCH_THRESHOLD,
        "mvp_ready": cache_match_rate >= 70,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "merged_works.json").write_text(json.dumps(works, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "merge_report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
