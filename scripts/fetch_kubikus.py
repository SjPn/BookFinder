"""Fetch Kubikus rating lists and book pages."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.kubikus_client import fetch_text
from bookfinder.parsers import kubikus as kb

OUT = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw" / "kubikus"

LISTS = [
    ("experts", "text.asp?rate=7"),
    ("reads", "text.asp?rate=1"),
    ("reviews", "text.asp?rate=3"),
    ("new", "text.asp?rate=2"),
]


def record_dict(record) -> dict:
    data = asdict(record)
    data["normalized_score"] = record.normalized_score
    return data


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--book-limit", type=int, default=400, help="Max book pages to fetch")
    parser.add_argument("--delay", type=float, default=1.2)
    args = parser.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    by_id: dict[str, dict] = {}

    for list_id, path in LISTS:
        print(f"list {list_id}")
        try:
            html = fetch_text(path, delay=args.delay)
            (RAW / f"list_{list_id}.html").write_text(html, encoding="utf-8")
            for record in kb.parse_list_page(html):
                by_id[record.external_id] = record_dict(record)
        except Exception as exc:  # noqa: BLE001
            print(f"  fail {list_id}: {exc}")

    pending = sorted(by_id.keys(), key=lambda x: int(x))
    if args.book_limit:
        pending = pending[: args.book_limit]

    print(f"books pending {len(pending)}")
    ok = fail = 0
    for idx, txid in enumerate(pending, start=1):
        cache = RAW / f"{txid}.html"
        try:
            if cache.exists():
                html = cache.read_text(encoding="utf-8", errors="ignore")
            else:
                html = fetch_text(f"textinfo.asp?txid={txid}", delay=args.delay)
                cache.write_text(html, encoding="utf-8")
            record = kb.parse_book_page(html, txid)
            if record:
                data = record_dict(record)
                data["lists"] = list({*(by_id.get(txid, {}).get("lists") or []),})
                by_id[txid] = data
                ok += 1
            else:
                fail += 1
        except Exception as exc:  # noqa: BLE001
            fail += 1
            if idx % 50 == 0:
                print(f"  fail {txid}: {exc}")
        if idx % 100 == 0:
            print(f"[{idx}] ok={ok} fail={fail}")

    books = list(by_id.values())
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "kubikus_books.json").write_text(json.dumps(books, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {len(books)} (pages ok={ok}, fail={fail})")


if __name__ == "__main__":
    main()
