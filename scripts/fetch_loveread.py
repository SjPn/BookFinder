"""Fetch LoveRead.ec listings (genres + recent pages) into loveread_books.json."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.http_client import RateLimitedClient
from bookfinder.parsers import loveread as lr

OUT = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw" / "loveread"


def record_dict(record) -> dict:
    data = asdict(record)
    data["normalized_score"] = record.normalized_score
    return data


def merge_records(by_id: dict[str, dict], records, list_name: str) -> int:
    added = 0
    for record in records:
        entry = record_dict(record)
        entry.setdefault("lists", []).append(list_name)
        prev = by_id.get(record.external_id)
        if prev:
            entry["lists"] = sorted(set(prev.get("lists", []) + entry["lists"]))
            if not entry.get("genres") and prev.get("genres"):
                entry["genres"] = prev["genres"]
            if entry.get("rating") is None and prev.get("rating") is not None:
                entry["rating"] = prev["rating"]
            if entry.get("vote_count") is None and prev.get("vote_count") is not None:
                entry["vote_count"] = prev["vote_count"]
        else:
            added += 1
        by_id[record.external_id] = entry
    return added


def fetch_page(client: RateLimitedClient, url: str, cache: Path) -> str:
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    response = client.get(url, referer=lr.BASE_URL)
    html = response.text
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(html, encoding="utf-8")
    return html


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--page-window", type=int, default=2500, help="Recent page.php pages to crawl")
    parser.add_argument("--min-page", type=int, default=100)
    args = parser.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    out_path = OUT / "loveread_books.json"
    by_id: dict[str, dict] = {}
    if out_path.exists():
        for item in json.loads(out_path.read_text(encoding="utf-8")):
            by_id[str(item["external_id"])] = item

    with RateLimitedClient(delay_sec=args.delay, warmup=False) as client:
        home_html = fetch_page(client, lr.BASE_URL, RAW / "home.html")
        merge_records(by_id, lr.parse_list_page(home_html, "home"), "home")
        print(f"after home: {len(by_id)}")

        genre_ids = lr.discover_genre_ids(home_html)
        for idx, genre_id in enumerate(genre_ids, start=1):
            url = lr.genre_url(genre_id)
            cache = RAW / f"genre_{genre_id}.html"
            try:
                html = fetch_page(client, url, cache)
                added = merge_records(by_id, lr.parse_list_page(html, f"genre:{genre_id}"), f"genre:{genre_id}")
                if added or idx % 25 == 0:
                    print(f"[genre {idx}/{len(genre_ids)}] id={genre_id} +{added}, total {len(by_id)}")
            except Exception as exc:  # noqa: BLE001
                print(f"genre {genre_id} fail: {exc}")
            time.sleep(0.05)

        max_page = lr.discover_max_page(home_html)
        start_page = max(args.min_page, max_page - args.page_window + 1)
        print(f"pages {start_page}..{max_page}")
        for page in range(start_page, max_page + 1):
            url = lr.page_url(page)
            cache = RAW / f"page_{page}.html"
            try:
                html = fetch_page(client, url, cache)
                books = lr.parse_list_page(html, f"page:{page}")
                if not books:
                    continue
                merge_records(by_id, books, f"page:{page}")
            except Exception as exc:  # noqa: BLE001
                if page % 200 == 0:
                    print(f"page {page} fail: {exc}")
            if page % 250 == 0:
                print(f"[page {page}] total {len(by_id)}")
                OUT.mkdir(parents=True, exist_ok=True)
                out_path.write_text(
                    json.dumps(list(by_id.values()), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            time.sleep(0.02)

    books = list(by_id.values())
    OUT.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(books, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"saved": len(books), "genres": len(genre_ids), "max_page": max_page}, ensure_ascii=False))


if __name__ == "__main__":
    main()
