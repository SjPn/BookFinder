"""Master enrichment pipeline: links, ratings, pages, rebuild."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run(name: str, *args: str) -> None:
    cmd = [sys.executable, str(SCRIPTS / name), *args]
    print(f"\n>>> {' '.join(cmd)}")
    subprocess.run(cmd, cwd=ROOT, check=False)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-fb2", action="store_true")
    parser.add_argument("--fb2-limit", type=int, default=0)
    parser.add_argument("--pages-limit", type=int, default=500)
    args = parser.parse_args()

    run("fetch_readrate.py", "--delay", "1.5")
    run("link_fw_downloads.py", "--fetch-missing", "--delay", "1.0")
    run("fetch_fantlab_api_cache.py", "--delay", "0.25", "--retry-failed")
    run("build_merged.py")
    if args.pages_limit:
        run("fetch_fw_catalog_pages.py", "--delay", "0.8", "--limit", str(args.pages_limit))
    run("build_expanded.py")
    if not args.skip_fb2:
        fb2_args = ["--delay", "2.0"]
        if args.fb2_limit:
            fb2_args.extend(["--limit", str(args.fb2_limit)])
        run("fetch_fb2.py", *fb2_args)
        run("build_expanded.py")


if __name__ == "__main__":
    main()
