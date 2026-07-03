"""Rebuild catalog from local caches (fast, no network)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run(name: str) -> None:
    subprocess.run([sys.executable, str(SCRIPTS / name)], cwd=ROOT, check=True)


def main() -> None:
    import os

    os.environ["PYTHONPATH"] = str(ROOT / "src")
    run("backfill_fw_catalog.py")
    run("build_merged.py")
    run("build_expanded.py")


if __name__ == "__main__":
    main()
