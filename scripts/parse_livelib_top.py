"""Parse saved livelib_top.html -> JSON."""

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.parsers import livelib

html = (ROOT / "data" / "raw" / "livelib_top.html").read_text(encoding="utf-8", errors="ignore")
books = livelib.parse_top_page(html)
out = ROOT / "data" / "processed" / "livelib_top.json"
payload = []
for b in books:
    d = asdict(b)
    d["normalized_score"] = b.normalized_score
    payload.append(d)
out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"parsed {len(books)} books -> {out}")
