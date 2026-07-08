"""Show DNA batch build progress."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.catalog import works_count
from bookfinder.dna_store import DNA_DIR, DNA_INDEX, DNA_PROGRESS

progress_path = DNA_PROGRESS
if progress_path.exists():
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
else:
    progress = {}

ok = sum(1 for value in progress.values() if value == "ok")
failed = [item for item in progress.items() if str(item[1]).startswith("fail")]
profiles = len(list(DNA_DIR.glob("*.json")))
total = works_count()
remaining = max(0, total - profiles)
pct = (profiles / total * 100) if total else 0.0

payload = {
    "catalog_total": total,
    "profiles_on_disk": profiles,
    "progress_entries": len(progress),
    "ok": ok,
    "failed": len(failed),
    "remaining": remaining,
    "percent": round(pct, 2),
    "index_exists": DNA_INDEX.exists(),
    "recent_failures": [work_id for work_id, _ in failed[-5:]],
}

print(f"ДНК: обработано {profiles}/{total} ({pct:.2f}%) | осталось {remaining} | ошибок {len(failed)}")
print(json.dumps(payload, ensure_ascii=False, indent=2))
