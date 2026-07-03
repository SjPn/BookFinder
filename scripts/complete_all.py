"""Run full data pipeline: fetch all sources and rebuild merged catalog."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> None:
    env = {**dict(**{"PYTHONPATH": str(ROOT / "src")})}
    import os

    os.environ["PYTHONPATH"] = str(ROOT / "src")

    run([PY, str(ROOT / "scripts" / "reparse_fantlab.py")])
    run([PY, str(ROOT / "scripts" / "parse_livelib_top.py")])
    run([PY, str(ROOT / "scripts" / "parse_fantasy_worlds_top.py")])
    run([PY, str(ROOT / "scripts" / "migrate_livelib_cache.py")])
    run([PY, str(ROOT / "scripts" / "fetch_fantasy_worlds.py"), "--delay", "1.5"])
    run([PY, str(ROOT / "scripts" / "fetch_fw_pages.py"), "--delay", "1.5"])
    run([PY, str(ROOT / "scripts" / "fetch_livelib_playwright.py"), "--delay", "4"])
    run([PY, str(ROOT / "scripts" / "build_merged.py")])
    run([PY, str(ROOT / "scripts" / "evaluate_cached.py")])


if __name__ == "__main__":
    main()
