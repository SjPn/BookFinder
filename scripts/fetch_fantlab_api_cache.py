"""Fetch FantLab work ratings via public API with retries."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.http_client import RateLimitedClient
from bookfinder.models import BookRecord
from bookfinder.parsers import fantasy_worlds as fw

OUT = ROOT / "data" / "processed"
CACHE = OUT / "fantlab_api_cache.json"
FW_BOOKS = ROOT / "data" / "raw" / "fw_books"


def load_fantlab_ids() -> set[str]:
    ids: set[str] = set()
    path = OUT / "fantlab_books.json"
    if path.exists():
        for item in json.loads(path.read_text(encoding="utf-8")):
            ids.add(str(item["external_id"]))
    catalog = OUT / "fw_catalog.json"
    if catalog.exists():
        for book in json.loads(catalog.read_text(encoding="utf-8")):
            if book.get("fantlab_id"):
                ids.add(str(book["fantlab_id"]))
    if FW_BOOKS.exists():
        for page in FW_BOOKS.glob("*.html"):
            fl_id = fw.extract_fantlab_id(page.read_text(encoding="utf-8", errors="ignore"))
            if fl_id:
                ids.add(fl_id)
    return ids


def main() -> None:
    import argparse
    import time

    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()

    cache: dict[str, dict] = {}
    if CACHE.exists():
        cache = json.loads(CACHE.read_text(encoding="utf-8"))

    pending = sorted(load_fantlab_ids())
    if not args.retry_failed:
        pending = [work_id for work_id in pending if work_id not in cache]

    print(f"pending {len(pending)}")
    ok = fail = 0

    with RateLimitedClient(delay_sec=args.delay, warmup=False, max_retries=8) as client:
        for idx, work_id in enumerate(pending, start=1):
            try:
                data = client.get_json(f"https://api.fantlab.ru/work{work_id}.json")
                rating = data.get("rating") or {}
                cache[work_id] = {
                    "rating": rating.get("rating"),
                    "votes": rating.get("voters"),
                    "title": data.get("work_name"),
                }
                ok += 1
                if idx % 50 == 0:
                    print(f"[{idx}] ok {ok} fail {fail}")
            except Exception as exc:  # noqa: BLE001
                fail += 1
                if args.retry_failed:
                    cache.pop(work_id, None)
                print(f"fail {work_id}: {exc}")
            time.sleep(args.delay)

    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {len(cache)} (ok {ok}, fail {fail})")


if __name__ == "__main__":
    main()
