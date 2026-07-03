"""Evaluate matching from cached raw/search HTML without new HTTP requests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from rapidfuzz import fuzz

from bookfinder.matcher import MATCH_THRESHOLD, find_best_match, match_with_search_map, score_pair
from bookfinder.models import BookRecord
from bookfinder.normalize import normalize_authors, normalize_title
from bookfinder.parsers import fantasy_worlds as fw
from bookfinder.parsers import livelib

DATA = ROOT / "data"
RAW = DATA / "raw"
OUT = DATA / "processed"


def load_fantlab() -> list[BookRecord]:
    path = OUT / "fantlab_books.json"
    books: list[BookRecord] = []
    for item in json.loads(path.read_text(encoding="utf-8")):
        item = dict(item)
        item.pop("normalized_score", None)
        book = BookRecord(**item)
        book.normalized_title = normalize_title(book.title)
        book.normalized_authors = normalize_authors(book.authors)
        books.append(book)
    return books


def _fantlab_from_filename(path: Path, fantlab_books: list[BookRecord]) -> BookRecord | None:
    stem = path.stem
    parts = stem.split("_", 1)
    prefix = parts[0]

    if prefix.isdigit() and len(prefix) >= 4:
        if prefix in {book.external_id for book in fantlab_books}:
            return next(book for book in fantlab_books if book.external_id == prefix)
        title_hint = parts[1].replace("_", " ") if len(parts) > 1 else ""
        if title_hint:
            scored = sorted(
                fantlab_books,
                key=lambda fl: fuzz.token_sort_ratio(normalize_title(fl.title), normalize_title(title_hint)),
                reverse=True,
            )
            if scored and fuzz.token_sort_ratio(normalize_title(scored[0].title), normalize_title(title_hint)) >= 85:
                return scored[0]
        idx = int(prefix)
        if 1 <= idx <= len(fantlab_books):
            return fantlab_books[idx - 1]
    return None


def load_search_map(fantlab_books: list[BookRecord]) -> dict[str, list[BookRecord]]:
    search_dir = RAW / "livelib_search"
    if not search_dir.exists():
        return {}

    by_id = {book.external_id: book for book in fantlab_books}
    mapping: dict[str, list[BookRecord]] = {}

    for path in sorted(search_dir.glob("*.html")):
        html = path.read_text(encoding="utf-8", errors="ignore")
        if "DDoS-Guard" in html or len(html) < 5000:
            continue

        fantlab_book = _fantlab_from_filename(path, fantlab_books)
        if fantlab_book is None:
            prefix = path.stem.split("_", 1)[0]
            if prefix.isdigit() and prefix in by_id:
                fantlab_book = by_id[prefix]
            else:
                continue

        parsed = livelib.parse_search_page(html, fantlab_book.title, fantlab_book.authors)
        if parsed:
            for record in parsed:
                record.normalized_title = normalize_title(record.title)
                record.normalized_authors = normalize_authors(record.authors)
            mapping.setdefault(fantlab_book.external_id, []).extend(parsed)

    return mapping


def main() -> None:
    fantlab_books = load_fantlab()
    search_map = load_search_map(fantlab_books)
    report = match_with_search_map(fantlab_books, search_map)

    matched_on_covered = [
        m for m in report.matched if m.fantlab.external_id in search_map
    ]
    covered = len(search_map)
    covered_match_rate = (len(matched_on_covered) / covered * 100) if covered else 0.0

    payload = {
        "fantlab_count": len(fantlab_books),
        "search_files_used": covered,
        "search_coverage_percent": round(covered / len(fantlab_books) * 100, 2),
        "match_rate_on_covered_percent": round(covered_match_rate, 2),
        "matched_on_covered": len(matched_on_covered),
        "projected_match_rate_if_full_coverage": round(covered_match_rate, 2),
        "mvp_ready_on_sample": covered_match_rate >= 70,
        "sample_matches": [
            {
                "score": round(m.score, 3),
                "fantlab": m.fantlab.title,
                "fantlab_authors": m.fantlab.authors,
                "livelib": m.livelib.title if m.livelib else None,
                "livelib_authors": m.livelib.authors if m.livelib else None,
            }
            for m in matched_on_covered[:20]
        ],
        "sample_failures": [
            {
                "fantlab": m.fantlab.title,
                "livelib": m.livelib.title if m.livelib else None,
                "score": round(m.score, 3),
            }
            for m in report.matched
            if m.fantlab.external_id in search_map
        ][:0],
    }

    failures = []
    for fantlab_id in search_map:
        fantlab_book = next(b for b in fantlab_books if b.external_id == fantlab_id)
        result = find_best_match(fantlab_book, search_map[fantlab_id], MATCH_THRESHOLD)
        if not result:
            continue
        score = result.score
        if score < 0.82:
            failures.append(
                {
                    "fantlab": fantlab_book.title,
                    "livelib": result.livelib.title if result.livelib else None,
                    "score": round(score, 3),
                }
            )
    payload["sample_failures"] = failures[:10]

    fw_matched = 0
    fw_dir = RAW / "fw_search"
    if fw_dir.exists():
        for path in fw_dir.glob("*.json"):
            fl = next((b for b in fantlab_books if b.external_id == path.stem), None)
            if fl is None:
                continue
            candidates = fw.parse_search_json(path.read_text(encoding="utf-8"))
            for c in candidates:
                c.normalized_title = normalize_title(c.title)
                c.normalized_authors = normalize_authors(c.authors)
            if find_best_match(fl, candidates, MATCH_THRESHOLD):
                fw_matched += 1
    payload["fantasy_worlds"] = {
        "search_cached": len(list(fw_dir.glob("*.json"))) if fw_dir.exists() else 0,
        "matched": fw_matched,
        "match_rate_percent": round(fw_matched / len(fantlab_books) * 100, 2) if fantlab_books else 0,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cached_eval.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
