"""Parse Fantasy-Worlds homepage popularity block."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.http_client import RateLimitedClient
from bookfinder.parsers import fantasy_worlds as fw

RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()

    cache = RAW / "fw_home.html"
    if args.fetch or not cache.exists():
        with RateLimitedClient(delay_sec=1.0, warmup=False) as client:
            html = client.get_text(fw.BASE_URL + "/")
        RAW.mkdir(parents=True, exist_ok=True)
        cache.write_text(html, encoding="utf-8")
    else:
        html = cache.read_text(encoding="utf-8")

    books = fw.parse_home_top(html)
    OUT.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "source": b.source,
            "external_id": b.external_id,
            "title": b.title,
            "authors": b.authors,
            "rank": b.rank,
            "url": b.url,
        }
        for b in books
    ]
    (OUT / "fantasy_worlds_top.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"saved {len(books)} books")


if __name__ == "__main__":
    main()
