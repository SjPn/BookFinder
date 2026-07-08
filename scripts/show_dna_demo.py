"""Dump human-readable DNA demo samples for review."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.dna_store import DNA_DIR

INDEX = ROOT / "data" / "processed" / "dna_index.json"
OUT = ROOT / "data" / "processed" / "dna_demo_samples.json"


def main() -> None:
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    items = index["items"]

    picks: list[dict] = []
    criteria = [
        ("romance", 8),
        ("thinking", 8),
        ("action", 8),
        ("magic", 7),
        ("darkness", 8),
        ("construction", 7),
    ]
    for key, thr in criteria:
        for item in items:
            if int((item.get("axes") or {}).get(key, 0)) >= thr and (item.get("ai_summary") or "").strip():
                if item not in picks:
                    picks.append(item)
                    break

    samples: list[dict] = []
    for item in picks[:6]:
        path = DNA_DIR / f"{item['work_id']}.json"
        full = json.loads(path.read_text(encoding="utf-8")) if path.exists() else item
        axes = full.get("axes") or {}
        top = sorted(axes.items(), key=lambda pair: -int(pair[1]))[:7]
        samples.append(
            {
                "work_id": full.get("work_id"),
                "title": full.get("title"),
                "authors": full.get("authors"),
                "ai_tagline": full.get("ai_tagline"),
                "ai_summary": full.get("ai_summary"),
                "themes": full.get("themes"),
                "labels": full.get("labels"),
                "top_axes": top,
                "reviews_summary": full.get("reviews_summary"),
                "sources": full.get("sources"),
                "embedding_dim": len(full.get("embedding") or []),
            }
        )

    theme_c: Counter[str] = Counter()
    for item in items:
        for theme in item.get("themes") or []:
            theme_c[str(theme).strip().lower()] += 1

    stats = {
        "profiles_index": index["count"],
        "with_ai_summary": sum(1 for item in items if (item.get("ai_summary") or "").strip()),
        "with_ai_tagline": sum(1 for item in items if (item.get("ai_tagline") or "").strip()),
        "with_embedding": sum(1 for item in items if item.get("has_embedding")),
        "used_annotation": sum(1 for item in items if (item.get("sources") or {}).get("annotation", 0) > 0),
        "used_reviews": sum(1 for item in items if (item.get("sources") or {}).get("reviews", 0) > 0),
        "used_text": sum(1 for item in items if (item.get("sources") or {}).get("text", 0) > 0),
        "top_themes": theme_c.most_common(20),
    }
    payload = {"stats": stats, "samples": samples}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
