from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bookfinder.http_client import RateLimitedClient
from bookfinder.matcher import MatchReport, match_books, match_search_results
from bookfinder.models import BookRecord
from bookfinder.parsers import fantlab, livelib

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
OUT_DIR = DATA_DIR / "processed"


def load_fantlab_cache() -> list[BookRecord] | None:
    path = OUT_DIR / "fantlab_books.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    books: list[BookRecord] = []
    for item in data:
        item = dict(item)
        item.pop("normalized_score", None)
        books.append(BookRecord(**item))
    return books


def record_to_dict(record: BookRecord) -> dict:
    data = asdict(record)
    data["normalized_score"] = record.normalized_score
    return data


def fetch_fantlab_ratings(client: RateLimitedClient, limit: int = 500) -> list[BookRecord]:
    all_records: list[BookRecord] = []
    seen_ids: set[str] = set()

    for work_type in (1, 2, 3, 4):
        url = fantlab.rating_url(work_type)
        cache_path = RAW_DIR / f"fantlab_type{work_type}.html"
        print(f"[FantLab] rating type={work_type} ...")

        if cache_path.exists():
            html = cache_path.read_text(encoding="utf-8", errors="ignore")
        else:
            html = client.get_text(url)
            cache_path.write_text(html, encoding="utf-8")

        batch = fantlab.parse_rating_page(html, work_type=work_type)
        print(f"  parsed {len(batch)} works")
        for record in batch:
            if record.external_id in seen_ids:
                continue
            seen_ids.add(record.external_id)
            all_records.append(record)
            if len(all_records) >= limit:
                return all_records

    if len(all_records) < limit:
        extra_url = "https://fantlab.ru/rating/work/popular?type=1&threshold=250"
        cache_path = RAW_DIR / "fantlab_popular.html"
        print("[FantLab] supplementing with popular rating ...")
        if cache_path.exists():
            html = cache_path.read_text(encoding="utf-8", errors="ignore")
        else:
            html = client.get_text(extra_url)
            cache_path.write_text(html, encoding="utf-8")
        for record in fantlab.parse_rating_page(html, work_type=1):
            if record.external_id in seen_ids:
                continue
            seen_ids.add(record.external_id)
            all_records.append(record)
            if len(all_records) >= limit:
                break

    return all_records[:limit]


def enrich_fantlab_genres(
    client: RateLimitedClient,
    records: list[BookRecord],
    max_details: int = 500,
) -> None:
    details_dir = RAW_DIR / "fantlab_works"
    details_dir.mkdir(parents=True, exist_ok=True)

    for idx, record in enumerate(records[:max_details], start=1):
        cache_path = details_dir / f"{record.external_id}.html"
        if cache_path.exists():
            html = cache_path.read_text(encoding="utf-8", errors="ignore")
        else:
            print(f"[FantLab] work detail {idx}/{min(len(records), max_details)} id={record.external_id}")
            try:
                html = client.get_text(fantlab.work_url(record.external_id))
                cache_path.write_text(html, encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                print(f"  skip {record.external_id}: {exc}")
                continue

        record.genres = fantlab.parse_work_page(html, record.external_id)
        if idx % 25 == 0:
            print(f"  genres fetched: {idx}")


def fetch_livelib_top(client: RateLimitedClient) -> list[BookRecord]:
    cache_path = RAW_DIR / "livelib_top.html"
    print("[LiveLib] top-100 page ...")

    records: list[BookRecord] = []
    if cache_path.exists():
        html = cache_path.read_text(encoding="utf-8", errors="ignore")
        records = livelib.parse_top_page(html)

    if len(records) < 20:
        try:
            html = client.get_text("https://www.livelib.ru/books/top")
            cache_path.write_text(html, encoding="utf-8")
            records = livelib.parse_top_page(html)
        except Exception as exc:  # noqa: BLE001
            print(f"  direct top fetch failed: {exc}")

    print(f"  parsed top records: {len(records)}")
    return records


def search_livelib_for_fantlab(
    client: RateLimitedClient,
    fantlab_books: list[BookRecord],
) -> dict[str, BookRecord]:
    from bookfinder.matcher import score_pair

    found_by_fantlab_id: dict[str, BookRecord] = {}
    search_dir = RAW_DIR / "livelib_search"
    search_dir.mkdir(parents=True, exist_ok=True)

    print(f"[LiveLib] searching {len(fantlab_books)} FantLab titles ...")
    for idx, fantlab_book in enumerate(fantlab_books, start=1):
        query = livelib.search_query(fantlab_book)
        safe_name = "".join(ch if ch.isalnum() else "_" for ch in fantlab_book.title)[:60]
        cache_path = search_dir / f"{fantlab_book.external_id}_{safe_name}.html"
        legacy_path = search_dir / f"{idx:04d}_{safe_name}.html"

        if cache_path.exists():
            html = cache_path.read_text(encoding="utf-8", errors="ignore")
        else:
            try:
                html = client.get_text(livelib.search_url(fantlab_book.title, fantlab_book.authors[0] if fantlab_book.authors else None))
                cache_path.write_text(html, encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                print(f"  search failed for '{query}': {exc}")
                continue

        if "DDoS-Guard" in html or len(html) < 5000:
            print(f"  blocked/empty response for '{query}'")
            continue

        candidates = livelib.parse_search_page(html, query, fantlab_book.authors)
        if not candidates:
            continue

        best = max(candidates, key=lambda c: score_pair(fantlab_book, c))
        found_by_fantlab_id[fantlab_book.external_id] = best

        if idx % 25 == 0:
            print(f"  searched {idx}, matched candidates {len(found_by_fantlab_id)}")

    print(f"  LiveLib search matches collected: {len(found_by_fantlab_id)}")
    return found_by_fantlab_id


def save_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_report_payload(report: MatchReport) -> dict:
    return {
        "total_fantlab": report.total_fantlab,
        "total_livelib": report.total_livelib,
        "matched_count": len(report.matched),
        "match_rate_percent": round(report.match_rate, 2),
        "threshold_passed_70": report.match_rate >= 70,
        "matched": [
            {
                "score": round(m.score, 3),
                "method": m.method,
                "fantlab": record_to_dict(m.fantlab),
                "livelib": record_to_dict(m.livelib) if m.livelib else None,
            }
            for m in report.matched
        ],
        "unmatched_fantlab": [record_to_dict(b) for b in report.unmatched_fantlab[:50]],
        "unmatched_livelib": [record_to_dict(b) for b in report.unmatched_livelib[:50]],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 0: parse FantLab + LiveLib and evaluate matching")
    parser.add_argument("--limit", type=int, default=500, help="FantLab works limit")
    parser.add_argument("--skip-genres", action="store_true", help="Skip FantLab work detail pages")
    parser.add_argument("--genre-sample", type=int, default=100, help="How many work pages to fetch for genres")
    parser.add_argument("--resume", action="store_true", help="Reuse cached FantLab JSON if present")
    parser.add_argument("--search-delay", type=float, default=1.0, help="Delay between LiveLib searches")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with RateLimitedClient(delay_sec=args.search_delay) as client:
        fantlab_books = load_fantlab_cache() if args.resume else None
        if fantlab_books is None:
            fantlab_books = fetch_fantlab_ratings(client, limit=args.limit)
            save_json(OUT_DIR / "fantlab_books.json", [record_to_dict(b) for b in fantlab_books])
        print(f"FantLab total: {len(fantlab_books)}")

        if not args.skip_genres and fantlab_books:
            enrich_fantlab_genres(client, fantlab_books, max_details=args.genre_sample)
            save_json(OUT_DIR / "fantlab_books_with_genres.json", [record_to_dict(b) for b in fantlab_books])

        livelib_top = fetch_livelib_top(client)
        save_json(OUT_DIR / "livelib_top.json", [record_to_dict(b) for b in livelib_top])

        livelib_search_map = search_livelib_for_fantlab(client, fantlab_books)
        livelib_search = list(livelib_search_map.values())
        save_json(OUT_DIR / "livelib_search_hits.json", [record_to_dict(b) for b in livelib_search])

        livelib_pool = {b.external_id: b for b in livelib_top}
        for book in livelib_search:
            livelib_pool[book.external_id] = book
        livelib_books = list(livelib_pool.values())

        report_search = match_search_results(fantlab_books, livelib_search_map)
        report_top = match_books(fantlab_books, livelib_top)
        report_all = match_books(fantlab_books, livelib_books)

        save_json(OUT_DIR / "match_report_search.json", build_report_payload(report_search))

        save_json(OUT_DIR / "match_report_top100.json", build_report_payload(report_top))
        save_json(OUT_DIR / "match_report_all.json", build_report_payload(report_all))

        summary = {
            "fantlab_count": len(fantlab_books),
            "livelib_top_count": len(livelib_top),
            "livelib_search_count": len(livelib_search),
            "livelib_search_coverage_percent": round(len(livelib_search_map) / len(fantlab_books) * 100, 2)
            if fantlab_books
            else 0,
            "livelib_pool_count": len(livelib_books),
            "match_rate_search_percent": round(report_search.match_rate, 2),
            "match_rate_vs_top_percent": round(report_top.match_rate, 2),
            "match_rate_vs_pool_percent": round(report_all.match_rate, 2),
            "mvp_ready": report_search.match_rate >= 70,
            "recommendation": (
                "Proceed to MVP" if report_search.match_rate >= 70 else "Improve normalization before MVP"
            ),
        }
        save_json(OUT_DIR / "phase0_summary.json", summary)

        print("\n=== PHASE 0 SUMMARY ===")
        for key, value in summary.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
