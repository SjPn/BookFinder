"""Build expanded catalog: FantLab merged works + Fantasy-Worlds-only books."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.parsers import fantasy_worlds as fw
from bookfinder.ratings import (
    aggregate_from_sources,
    clean_fl_block,
    clean_fw_block,
    clean_ll_block,
    valid_rating,
)

OUT = ROOT / "data" / "processed"
FW_BOOKS = ROOT / "data" / "raw" / "fw_books"
FL_API_CACHE = OUT / "fantlab_api_cache.json"
FB2_DIR = ROOT / "data" / "books" / "fb2"


def load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_fl_api() -> dict[str, dict]:
    if not FL_API_CACHE.exists():
        return {}
    return json.loads(FL_API_CACHE.read_text(encoding="utf-8"))


def fb2_local_path(fw_id: str | None) -> str | None:
    if not fw_id:
        return None
    path = FB2_DIR / f"{fw_id}.fb2.zip"
    return str(path.relative_to(ROOT)).replace("\\", "/") if path.exists() else None


def fw_rating(book: dict) -> tuple[float | None, int | None, list[str], str | None]:
    book_id = str(book["id"])
    genres = list(book.get("genres") or [])
    fantlab_id = book.get("fantlab_id")

    if book.get("rating") is not None:
        return book.get("rating"), book.get("votes"), genres, fantlab_id

    path = FW_BOOKS / f"{book_id}.html"
    if path.exists():
        html = path.read_text(encoding="utf-8", errors="ignore")
        record = fw.parse_book_page(html)
        if record:
            genres = record.genres or genres
            fantlab_id = fantlab_id or fw.extract_fantlab_id(html)
            if record.rating is not None:
                return record.rating, record.vote_count, genres, fantlab_id

    return None, None, genres, fantlab_id


def _source_triples(entry: dict) -> list[tuple[str, float, int | None]]:
    sources: list[tuple[str, float, int | None]] = []
    fl = entry.get("fantlab") or entry.get("fantlab_link")
    if fl and fl.get("rating") is not None:
        sources.append(("fantlab", float(fl["rating"]), fl.get("votes")))
    ll = entry.get("livelib")
    if ll and ll.get("rating") is not None:
        sources.append(("livelib", float(ll["rating"]), ll.get("votes")))
    fw_info = entry.get("fantasy_worlds")
    if fw_info and fw_info.get("rating") is not None:
        sources.append(("fantasy_worlds", float(fw_info["rating"]), fw_info.get("votes")))
    return sources


def sanitize_entry(entry: dict, fl_api: dict[str, dict]) -> dict:
    fl_id = (entry.get("fantlab") or {}).get("id") or entry.get("fantlab_link", {}).get("id")
    if fl_id and fl_id in fl_api:
        api = fl_api[fl_id]
        if api.get("rating") is not None:
            fl_block = dict(entry.get("fantlab") or {"id": fl_id})
            if fl_block.get("rating") is None:
                fl_block["rating"] = api["rating"]
                fl_block["votes"] = api.get("votes")
                entry["fantlab"] = fl_block

    agg = aggregate_from_sources(_source_triples(entry))
    entry["aggregate_rating"] = round(agg, 2) if agg is not None else None

    if entry.get("fantlab"):
        entry["fantlab"] = clean_fl_block(entry["fantlab"])
        if not entry["fantlab"]:
            entry.pop("fantlab", None)
    if entry.get("livelib"):
        entry["livelib"] = clean_ll_block(entry["livelib"])
        if not entry["livelib"]:
            entry.pop("livelib", None)
    if entry.get("fantasy_worlds"):
        entry["fantasy_worlds"] = clean_fw_block(entry["fantasy_worlds"])
        if not entry["fantasy_worlds"]:
            entry.pop("fantasy_worlds", None)
    if entry.get("fantlab_link"):
        link = entry["fantlab_link"]
        if valid_rating("fantlab", link.get("rating"), link.get("votes")):
            entry["fantlab_link"] = {
                "id": link["id"],
                "rating": link["rating"],
                "votes": link.get("votes"),
            }
        else:
            entry["fantlab_link"] = {"id": link["id"]}

    fw_info = entry.get("fantasy_worlds") or {}
    fw_id = fw_info.get("id")
    if fw_id and not entry.get("download_url"):
        dl = fw_info.get("download_url") or fw.download_url(fw_id)
        entry["download_url"] = dl
        if entry.get("fantasy_worlds"):
            entry["fantasy_worlds"]["download_url"] = dl

    local = fb2_local_path(str(fw_id) if fw_id else None)
    if local:
        entry["fb2_local"] = local
    else:
        entry.pop("fb2_local", None)

    return entry


def main() -> None:
    merged = load_json(OUT / "merged_works.json")
    catalog = load_json(OUT / "fw_catalog.json")
    fl_api = load_fl_api()
    readrate = {item["external_id"]: item for item in load_json(OUT / "readrate_books.json")}

    linked_fw_ids = {
        str(entry.get("fantasy_worlds", {}).get("id"))
        for entry in merged
        if entry.get("fantasy_worlds", {}).get("id")
    }

    expanded = [sanitize_entry(dict(entry), fl_api) for entry in merged]
    added = 0
    rated_added = 0

    for book in catalog:
        book_id = str(book["id"])
        if book_id in linked_fw_ids:
            continue

        rating, votes, genres, fantlab_id = fw_rating(book)
        fl_rating = fl_api.get(str(fantlab_id), {}) if fantlab_id else {}

        entry = {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"fw:{book_id}")),
            "title": book["title"],
            "authors": book.get("authors", []),
            "genres": genres,
            "year": book.get("year"),
            "fantasy_worlds": {
                "id": book_id,
                "rating": rating,
                "votes": votes,
                "url": book.get("url") or fw.book_url(book_id),
                "download_url": book.get("download_url") or fw.download_url(book_id),
            },
            "download_url": book.get("download_url") or fw.download_url(book_id),
            "source_origin": "fantasy_worlds",
        }
        if fantlab_id and fl_rating.get("rating") is not None:
            entry["fantlab_link"] = {
                "id": str(fantlab_id),
                "rating": fl_rating.get("rating"),
                "votes": fl_rating.get("votes"),
            }

        entry = sanitize_entry(entry, fl_api)
        expanded.append(entry)
        added += 1
        if entry.get("aggregate_rating") is not None:
            rated_added += 1

    expanded.sort(
        key=lambda item: (item.get("aggregate_rating") is None, -(item.get("aggregate_rating") or 0)),
    )

    (OUT / "expanded_works.json").write_text(json.dumps(expanded, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "fantlab_merged": len(merged),
        "fw_only_added": added,
        "fw_only_rated": rated_added,
        "total": len(expanded),
        "total_rated": sum(1 for item in expanded if item.get("aggregate_rating")),
        "with_download": sum(1 for item in expanded if item.get("download_url")),
        "with_fb2_local": sum(1 for item in expanded if item.get("fb2_local")),
        "readrate_indexed": len(readrate),
        "rating_policy": "parsed sources only, min votes: fantlab=10, livelib=5, fw=10",
    }
    (OUT / "expanded_report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
