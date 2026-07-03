"""Download FB2 files from Fantasy-Worlds for catalog entries."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.http_client import RateLimitedClient
from bookfinder.parsers import fantasy_worlds as fw

OUT = ROOT / "data" / "processed"
FB2_DIR = ROOT / "data" / "books" / "fb2"
PROGRESS = OUT / "fb2_download_progress.json"


def collect_fw_ids() -> list[str]:
    ids: set[str] = set()
    for path in (OUT / "merged_works.json", OUT / "expanded_works.json", OUT / "fw_catalog.json"):
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else []
        for item in items:
            if isinstance(item, dict) and item.get("id") and path.name == "fw_catalog.json":
                ids.add(str(item["id"]))
                continue
            fw_info = item.get("fantasy_worlds") or {}
            if fw_info.get("id"):
                ids.add(str(fw_info["id"]))
    links = OUT / "fw_download_links.json"
    if links.exists():
        for value in json.loads(links.read_text(encoding="utf-8")).values():
            if value.get("fw_id"):
                ids.add(str(value["fw_id"]))
    return sorted(ids, key=int)


def save_progress(done: dict[str, str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text(json.dumps(done, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()

    FB2_DIR.mkdir(parents=True, exist_ok=True)
    progress: dict[str, str] = {}
    if PROGRESS.exists():
        progress = json.loads(PROGRESS.read_text(encoding="utf-8"))

    pending = []
    for book_id in collect_fw_ids():
        target = FB2_DIR / f"{book_id}.fb2.zip"
        if target.exists():
            continue
        if book_id in progress and not args.retry_failed:
            if progress[book_id] == "ok":
                continue
        pending.append(book_id)

    if args.limit:
        pending = pending[: args.limit]

    print(f"pending {len(pending)}")
    ok = skip = fail = 0

    with RateLimitedClient(delay_sec=args.delay, warmup=False, max_retries=8) as client:
        for idx, book_id in enumerate(pending, start=1):
            url = fw.download_url(book_id)
            target = FB2_DIR / f"{book_id}.fb2.zip"
            try:
                response = client.get(url, referer=fw.book_url(book_id))
                content = response.content
                if len(content) < 500 or b"<html" in content[:200].lower():
                    progress[book_id] = "skip"
                    skip += 1
                    print(f"[{idx}] skip {book_id}")
                    continue
                target.write_bytes(content)
                progress[book_id] = "ok"
                ok += 1
                print(f"[{idx}] ok {book_id} ({len(content)} bytes)")
            except Exception as exc:  # noqa: BLE001
                progress[book_id] = f"fail:{exc}"
                fail += 1
                print(f"[{idx}] fail {book_id}: {exc}")

            if idx % 20 == 0:
                save_progress(progress)

    save_progress(progress)
    print(f"saved {ok}, skip {skip}, fail {fail}")


if __name__ == "__main__":
    main()
