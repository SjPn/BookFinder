"""Fetch FantLab work ratings via public API with stable caching."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.http_client import RateLimitedClient
from bookfinder.parsers import fantasy_worlds as fw
from bookfinder.stable_fetch import fetch_fantlab_work, probe_url

OUT = ROOT / "data" / "processed"
CACHE = OUT / "fantlab_api_cache.json"
API_RAW = ROOT / "data" / "raw" / "fantlab_api"
HTML_RAW = ROOT / "data" / "raw" / "fantlab_work"
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

    parser = argparse.ArgumentParser()
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--html-only", action="store_true", help="Skip API, use HTML pages only")
    parser.add_argument("--force-run", action="store_true", help="Run even if FantLab probe fails")
    args = parser.parse_args()

    if not args.force_run:
        from bookfinder.dns_resolve import is_poisoned, local_ip

        if is_poisoned("fantlab.ru"):
            print(f"DNS: fantlab.ru -> {local_ip('fantlab.ru')} (подмена), пробуем 8.8.8.8")
        if not probe_url(RateLimitedClient(delay_sec=0), "https://fantlab.ru/"):
            print(
                "FantLab недоступен (VPN выключен или IP заблокирован). "
                "Включите VPN и задайте прокси: $env:HTTPS_PROXY='http://127.0.0.1:7890' "
                "или запустите на VPS: python scripts/fetch_fantlab_api_cache.py --force-run"
            )
            return

    cache: dict[str, dict] = {}
    if CACHE.exists():
        cache = json.loads(CACHE.read_text(encoding="utf-8"))

    pending = sorted(load_fantlab_ids())
    if not args.retry_failed:
        pending = [work_id for work_id in pending if work_id not in cache]
    if args.limit:
        pending = pending[: args.limit]

    print(f"pending {len(pending)}")
    ok = fail = skip = 0

    with RateLimitedClient(delay_sec=None, warmup=True, max_retries=8) as client:
        for idx, work_id in enumerate(pending, start=1):
            try:
                data = fetch_fantlab_work(
                    client,
                    work_id,
                    API_RAW / f"{work_id}.json",
                    HTML_RAW / f"{work_id}.html",
                    force=args.retry_failed,
                    html_only=args.html_only,
                )
                rating = data.get("rating") or {}
                cache[work_id] = {
                    "rating": rating.get("rating"),
                    "votes": rating.get("voters"),
                    "title": data.get("work_name"),
                    "source": data.get("source", "api"),
                }
                ok += 1
            except RuntimeError as exc:
                if "Circuit open" in str(exc):
                    print(f"circuit pause, saved progress ({ok} ok)")
                    break
                fail += 1
                print(f"fail {work_id}: {exc}")
            except Exception as exc:  # noqa: BLE001
                fail += 1
                if args.retry_failed:
                    cache.pop(work_id, None)
                print(f"fail {work_id}: {exc}")

            if idx % 40 == 0:
                OUT.mkdir(parents=True, exist_ok=True)
                CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"[{idx}] ok {ok} fail {fail}")

    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {len(cache)} (ok {ok}, fail {fail}, skip {skip})")


if __name__ == "__main__":
    main()
