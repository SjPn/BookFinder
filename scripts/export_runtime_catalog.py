"""Build compact works_index.json / works_details.json / genres.json from expanded_works.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.runtime_catalog import write_runtime_catalog

OUT = ROOT / "data" / "processed"


def main() -> None:
    source = OUT / "expanded_works.json"
    if not source.exists():
        raise SystemExit(f"Missing {source}")

    works = json.loads(source.read_text(encoding="utf-8"))
    summary = write_runtime_catalog(works, OUT)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
