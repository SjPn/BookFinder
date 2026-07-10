"""Audit and repair false Fantasy-Worlds links / descriptions / DNA.

Compares each work's linked FW book against title+author using the hardened matcher.
Removes bad FW links, clears poisoned descriptions, and deletes bad DNA profiles.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.dna_store import DNA_DIR, build_index, load_progress, profile_path, save_progress
from bookfinder.matcher import score_pair
from bookfinder.models import BookRecord
from bookfinder.normalize import normalize_authors, normalize_title

DATA = ROOT / "data" / "processed"
FW_CATALOG = DATA / "fw_catalog.json"
EXPANDED = DATA / "expanded_works.json"
DETAILS = DATA / "works_details.json"
REPORT = DATA / "fw_link_audit.json"


def _record(title: str, authors: list[str], external_id: str = "x") -> BookRecord:
    return BookRecord(
        source="audit",
        external_id=external_id,
        title=title or "",
        authors=list(authors or []),
        normalized_title=normalize_title(title or ""),
        normalized_authors=normalize_authors(list(authors or [])),
    )


def load_fw_catalog() -> dict[str, dict]:
    if not FW_CATALOG.exists():
        raise SystemExit(f"Missing {FW_CATALOG}")
    rows = json.loads(FW_CATALOG.read_text(encoding="utf-8"))
    return {str(row["id"]): row for row in rows if row.get("id")}


def audit_works(works: list[dict], fw_by_id: dict[str, dict], threshold: float) -> list[dict]:
    bad: list[dict] = []
    for work in works:
        fw = work.get("fantasy_worlds") or {}
        fw_id = str(fw.get("id") or "")
        if not fw_id:
            continue
        fw_book = fw_by_id.get(fw_id)
        if not fw_book:
            bad.append(
                {
                    "work_id": work["id"],
                    "title": work.get("title"),
                    "authors": work.get("authors"),
                    "fw_id": fw_id,
                    "reason": "fw_id_missing_in_catalog",
                    "score": 0.0,
                }
            )
            continue

        left = _record(str(work.get("title") or ""), list(work.get("authors") or []), work["id"])
        right = _record(
            str(fw_book.get("title") or ""),
            list(fw_book.get("authors") or []),
            fw_id,
        )
        score = score_pair(left, right)
        if score < threshold:
            bad.append(
                {
                    "work_id": work["id"],
                    "title": work.get("title"),
                    "authors": work.get("authors"),
                    "fw_id": fw_id,
                    "fw_title": fw_book.get("title"),
                    "fw_authors": fw_book.get("authors"),
                    "reason": "title_author_mismatch",
                    "score": round(score, 4),
                    "description_source": work.get("description_source"),
                }
            )
    return bad


def repair(
    works: list[dict],
    bad: list[dict],
    *,
    clear_dna: bool,
) -> dict:
    bad_ids = {row["work_id"] for row in bad}
    cleared_desc = 0
    cleared_fw = 0
    cleared_dna = 0
    details: dict = {}
    if DETAILS.exists():
        details = json.loads(DETAILS.read_text(encoding="utf-8"))

    for work in works:
        if work["id"] not in bad_ids:
            continue
        if work.get("fantasy_worlds"):
            work.pop("fantasy_worlds", None)
            cleared_fw += 1
        if work.get("download_url") and "fantasy-worlds.net" in str(work.get("download_url")):
            work.pop("download_url", None)
        if work.get("fb2_local"):
            work.pop("fb2_local", None)
        if work.get("description_source") == "fantasy_worlds":
            work.pop("description", None)
            work.pop("description_source", None)
            cleared_desc += 1
            details.pop(work["id"], None)

        if clear_dna:
            path = profile_path(work["id"])
            if path.exists():
                path.unlink()
                cleared_dna += 1

    if clear_dna and bad_ids:
        progress = load_progress()
        for work_id in bad_ids:
            progress.pop(work_id, None)
        save_progress(progress)

    EXPANDED.write_text(json.dumps(works, ensure_ascii=False, indent=2), encoding="utf-8")
    DETAILS.write_text(json.dumps(details, ensure_ascii=False), encoding="utf-8")
    return {
        "bad_links": len(bad_ids),
        "cleared_fw": cleared_fw,
        "cleared_descriptions": cleared_desc,
        "cleared_dna": cleared_dna,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit/repair false Fantasy-Worlds links")
    parser.add_argument("--threshold", type=float, default=0.82)
    parser.add_argument("--repair", action="store_true", help="Remove bad FW links and poisoned descriptions")
    parser.add_argument("--clear-dna", action="store_true", help="Delete DNA profiles for bad matches")
    parser.add_argument("--reindex-dna", action="store_true", help="Rebuild dna_index.json after DNA cleanup")
    parser.add_argument("--limit", type=int, default=0, help="Print first N bad examples")
    args = parser.parse_args()

    fw_by_id = load_fw_catalog()
    works = json.loads(EXPANDED.read_text(encoding="utf-8"))
    bad = audit_works(works, fw_by_id, args.threshold)
    REPORT.write_text(json.dumps({"count": len(bad), "items": bad}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"audited_works": len(works), "bad_fw_links": len(bad), "report": str(REPORT)}, ensure_ascii=False))
    show = bad[: args.limit] if args.limit > 0 else bad[:15]
    for row in show:
        print(
            f"- {row.get('title')} / {', '.join(row.get('authors') or [])} "
            f"<= FW {row.get('fw_id')} {row.get('fw_title')} / {', '.join(row.get('fw_authors') or [])} "
            f"score={row.get('score')} ({row.get('reason')})",
            flush=True,
        )

    if args.repair:
        stats = repair(works, bad, clear_dna=args.clear_dna)
        print(json.dumps({"repaired": stats}, ensure_ascii=False), flush=True)
        if args.clear_dna and args.reindex_dna:
            index = build_index()
            print(json.dumps({"dna_indexed": index["count"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
