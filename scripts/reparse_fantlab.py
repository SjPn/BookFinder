"""Re-parse FantLab from cached HTML and save JSON."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.models import BookRecord
from bookfinder.parsers import fantlab

RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"


def main() -> None:
    all_records: list[BookRecord] = []
    seen: set[str] = set()

    for work_type in (1, 2, 3, 4):
        path = RAW / f"fantlab_type{work_type}.html"
        if not path.exists():
            print(f"missing {path}")
            continue
        html = path.read_text(encoding="utf-8", errors="ignore")
        batch = fantlab.parse_rating_page(html, work_type=work_type)
        print(f"type {work_type}: {len(batch)}, authors sample: {batch[0].authors if batch else []}")
        for record in batch:
            if record.external_id in seen:
                continue
            seen.add(record.external_id)
            all_records.append(record)

    popular = RAW / "fantlab_popular.html"
    if popular.exists():
        for record in fantlab.parse_rating_page(popular.read_text(encoding="utf-8", errors="ignore"), 1):
            if record.external_id not in seen:
                seen.add(record.external_id)
                all_records.append(record)

    payload = []
    for record in all_records:
        item = asdict(record)
        item["normalized_score"] = record.normalized_score
        payload.append(item)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "fantlab_books.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", len(payload))


if __name__ == "__main__":
    main()
