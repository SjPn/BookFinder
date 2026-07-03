"""Stable enrichment pipeline with anti-block fetch policies."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run(name: str, *args: str) -> bool:
    cmd = [sys.executable, str(SCRIPTS / name), *args]
    print(f"\n>>> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT)
    return result.returncode == 0


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-fb2", action="store_true")
    parser.add_argument("--skip-livelib", action="store_true")
    parser.add_argument("--skip-fantlab", action="store_true")
    parser.add_argument("--fw-pages-limit", type=int, default=1500)
    parser.add_argument("--fl-api-limit", type=int, default=500)
    args = parser.parse_args()

    run("crawl_fw_catalog.py", "--bigrams", "--trigrams")
    if not args.skip_fantlab:
        run("fetch_fantlab_api_cache.py", "--retry-failed", "--limit", str(args.fl_api_limit))
    if args.fw_pages_limit:
        run("fetch_fw_catalog_pages.py", "--limit", str(args.fw_pages_limit))
    run("backfill_fw_catalog.py")
    run("build_merged.py")
    run("build_expanded.py")
    run("index_fw_reviews_cache.py")
    run("build_work_reviews.py")
    run("fetch_kubikus.py", "--book-limit", "500")
    run("fetch_bookmix.py", "--book-limit", "200")
    if not args.skip_livelib:
        run("fetch_livelib_playwright.py", "--delay", "5")
    if not args.skip_livelib:
        run("fetch_reviews.py", "--merged-only", "--limit", "300")
    if not args.skip_fb2:
        run("fetch_fb2.py", "--delay", "1.5", "--limit", "500")
    run("rebuild_catalog.py")


if __name__ == "__main__":
    main()
