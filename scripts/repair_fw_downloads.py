"""Aggressive FW search for FantLab books still missing download."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.http_client import RateLimitedClient
from bookfinder.matcher import find_best_match
from bookfinder.models import BookRecord
from bookfinder.normalize import normalize_authors, normalize_title
from bookfinder.parsers import fantasy_worlds as fw

OUT = ROOT / "data" / "processed"
SEARCH_DIR = ROOT / "data" / "raw" / "fw_search"
LINKS_PATH = OUT / "fw_download_links.json"
THRESHOLD = 0.62


def load_links() -> dict[str, dict]:
    if LINKS_PATH.exists():
        return json.loads(LINKS_PATH.read_text(encoding="utf-8"))
    return {}


def save_links(links: dict[str, dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    LINKS_PATH.write_text(json.dumps(links, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()

    expanded = json.loads((OUT / "expanded_works.json").read_text(encoding="utf-8"))
    links = load_links()

    pending: list[tuple[str, str, list[str]]] = []
    for item in expanded:
        if item.get("download_url"):
            continue
        fl = item.get("fantlab") or {}
        fl_id = fl.get("id")
        if not fl_id:
            continue
        if links.get(fl_id, {}).get("fw_id"):
            continue
        pending.append((fl_id, item["title"], item.get("authors") or []))

    print(f"pending {len(pending)}")

    with RateLimitedClient(delay_sec=args.delay, warmup=False) as client:
        for idx, (fl_id, title, authors) in enumerate(pending, start=1):
            queries = [
                f"{authors[0]} {title}" if authors else title,
                title,
                authors[0] if authors else title,
            ]
            best_match = None
            best_score = 0.0

            fl_book = BookRecord(
                source="fantlab",
                external_id=fl_id,
                title=title,
                authors=authors,
                normalized_title=normalize_title(title),
                normalized_authors=normalize_authors(authors),
            )

            for query in queries:
                try:
                    data = client.get_json(fw.search_url(query), referer="https://fantasy-worlds.net/lib/")
                    candidates = fw.parse_search_json(data)
                    for candidate in candidates:
                        candidate.normalized_title = normalize_title(candidate.title)
                        candidate.normalized_authors = normalize_authors(candidate.authors)
                    result = find_best_match(fl_book, candidates, THRESHOLD) if candidates else None
                    if result and result.score > best_score:
                        best_score = result.score
                        best_match = result
                except Exception:  # noqa: BLE001
                    continue

            if best_match:
                fw_book = best_match.livelib  # type: ignore[assignment]
                links[fl_id] = {
                    "fw_id": fw_book.external_id,
                    "title": fw_book.title,
                    "download_url": fw.download_url(fw_book.external_id),
                    "url": fw.book_url(fw_book.external_id),
                    "match_score": round(best_score, 3),
                    "method": "aggressive",
                }
                print(f"[{idx}] linked {title} -> {fw_book.external_id} ({best_score:.2f})")
            else:
                links[fl_id] = {"fw_id": None, "method": "aggressive"}
                print(f"[{idx}] no match: {title}")

            if idx % 20 == 0:
                save_links(links)

    save_links(links)
    matched = sum(1 for value in links.values() if value.get("fw_id"))
    print(f"total linked {matched}")


if __name__ == "__main__":
    main()
