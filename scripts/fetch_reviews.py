"""Fetch and aggregate book reviews from FantLab, LiveLib, Fantasy-Worlds."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.http_client import RateLimitedClient
from bookfinder.parsers import fantasy_worlds as fw
from bookfinder.parsers.reviews import (
    dedupe_reviews,
    livelib_reviews_url,
    parse_fantasy_worlds_comments,
    parse_fantlab_api_responses,
    parse_fantlab_work_page,
    parse_livelib_reviews,
)
from bookfinder.reviews_store import load_fw_reviews_by_id, load_work_reviews, save_work_reviews

OUT = ROOT / "data" / "processed"
FW_BOOKS = ROOT / "data" / "raw" / "fw_books"
FL_WORK = ROOT / "data" / "raw" / "fantlab_work"
LL_REVIEWS = ROOT / "data" / "raw" / "livelib_reviews"

TARGET_MIN = 5
TARGET_MAX = 10


def load_works() -> list[dict]:
    for name in ("expanded_works.json", "merged_works.json"):
        path = OUT / name
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return []


def fw_reviews_for_id(fw_id: str, fw_cache: dict[str, list]) -> list[dict]:
    if fw_id in fw_cache:
        return list(fw_cache[fw_id])
    path = FW_BOOKS / f"{fw_id}.html"
    if path.exists():
        return parse_fantasy_worlds_comments(path.read_text(encoding="utf-8", errors="ignore"), fw_id)
    return []


def fetch_fw_reviews(client: RateLimitedClient, fw_id: str, fw_cache: dict[str, list]) -> list[dict]:
    existing = fw_reviews_for_id(fw_id, fw_cache)
    if existing:
        return existing
    try:
        html = client.get_text(fw.book_url(fw_id), referer="https://fantasy-worlds.net/lib/")
        FW_BOOKS.mkdir(parents=True, exist_ok=True)
        (FW_BOOKS / f"{fw_id}.html").write_text(html, encoding="utf-8")
        reviews = parse_fantasy_worlds_comments(html, fw_id)
        if reviews:
            fw_cache[fw_id] = reviews
        return reviews
    except Exception:  # noqa: BLE001
        return []


def fetch_fantlab_reviews(client: RateLimitedClient, work_id: str) -> list[dict]:
    FL_WORK.mkdir(parents=True, exist_ok=True)
    cache = FL_WORK / f"{work_id}.html"
    reviews: list[dict] = []

    for api_suffix in ("responses.json", "workreviews.json", "reviews.json"):
        try:
            data = client.get_json(f"https://api.fantlab.ru/work{work_id}/{api_suffix}")
            reviews.extend(parse_fantlab_api_responses(data))
            if len(reviews) >= TARGET_MIN:
                return reviews
        except Exception:  # noqa: BLE001
            continue

    try:
        if cache.exists():
            html = cache.read_text(encoding="utf-8", errors="ignore")
        else:
            html = client.get_text(f"https://fantlab.ru/work{work_id}", referer="https://fantlab.ru/")
            cache.write_text(html, encoding="utf-8")
        reviews.extend(parse_fantlab_work_page(html, work_id))
    except Exception:  # noqa: BLE001
        pass
    return reviews


def fetch_livelib_reviews(client: RateLimitedClient, book_url: str, book_id: str) -> list[dict]:
    LL_REVIEWS.mkdir(parents=True, exist_ok=True)
    reviews_url = livelib_reviews_url(book_url)
    cache = LL_REVIEWS / f"{book_id}.html"

    try:
        if cache.exists():
            html = cache.read_text(encoding="utf-8", errors="ignore")
        else:
            html = client.get_text(reviews_url, referer="https://www.livelib.ru/")
            cache.write_text(html, encoding="utf-8")
        return parse_livelib_reviews(html, reviews_url)
    except Exception:  # noqa: BLE001
        return []


def collect_for_work(client: RateLimitedClient, work: dict, fw_cache: dict[str, list]) -> tuple[list[dict], list[str]]:
    reviews: list[dict] = []
    tried: list[str] = []

    fw_info = work.get("fantasy_worlds") or {}
    fw_id = fw_info.get("id")
    if fw_id:
        tried.append("fantasy_worlds")
        reviews.extend(fw_reviews_for_id(str(fw_id), fw_cache))

    fl = work.get("fantlab") or {}
    fl_id = fl.get("id")
    if fl_id:
        tried.append("fantlab")
        reviews.extend(fetch_fantlab_reviews(client, str(fl_id)))

    ll = work.get("livelib") or {}
    ll_url = ll.get("url")
    ll_id = ll.get("id")
    if ll_url and ll_id:
        tried.append("livelib")
        reviews.extend(fetch_livelib_reviews(client, ll_url, str(ll_id)))

    reviews = dedupe_reviews(reviews)

    if len(reviews) < TARGET_MIN and fw_id:
        tried.append("fantasy_worlds_fetch")
        reviews = dedupe_reviews(reviews + fetch_fw_reviews(client, str(fw_id), fw_cache))

    if len(reviews) < TARGET_MIN and ll_url and ll_id:
        tried.append("livelib_fetch")
        reviews = dedupe_reviews(reviews + fetch_livelib_reviews(client, ll_url, str(ll_id)))

    return reviews[:TARGET_MAX] if reviews else [], tried


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--merged-only", action="store_true", help="Only FantLab merged works")
    args = parser.parse_args()

    works = load_works()
    if args.merged_only:
        works = [w for w in works if w.get("fantlab")]

    pending = works
    if args.limit:
        pending = pending[: args.limit]

    fw_cache = load_fw_reviews_by_id()
    store = load_work_reviews()
    ok = empty = 0

    with RateLimitedClient(delay_sec=args.delay, warmup=False) as client:
        for idx, work in enumerate(pending, start=1):
            work_id = work["id"]
            if work_id in store and store[work_id].get("count", 0) >= TARGET_MIN:
                continue

            reviews, tried = collect_for_work(client, work, fw_cache)
            store[work_id] = {
                "count": len(reviews),
                "sources_tried": tried,
                "reviews": reviews,
            }
            if reviews:
                ok += 1
                print(f"[{idx}] {work['title'][:50]}: {len(reviews)} reviews")
            else:
                empty += 1

            if idx % 25 == 0:
                save_work_reviews(store)

    from bookfinder.reviews_store import save_fw_reviews_by_id

    save_fw_reviews_by_id(fw_cache)
    save_work_reviews(store)
    print(json.dumps({"processed": len(pending), "with_reviews": ok, "empty": empty}, ensure_ascii=False))


if __name__ == "__main__":
    main()
