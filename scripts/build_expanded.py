"""Build expanded catalog: FantLab merged works + Fantasy-Worlds-only books."""

from __future__ import annotations

import json
import sys
import uuid
from dataclasses import fields
from pathlib import Path

from bookfinder.matcher import MATCH_THRESHOLD, find_best_match, score_pair
from bookfinder.models import BookRecord
from bookfinder.normalize import normalize_authors, normalize_title
from bookfinder.descriptions import (
    extract_bookmix_description,
    extract_fantlab_description,
    extract_fw_description,
)
from bookfinder.parsers import fantasy_worlds as fw
from bookfinder.ratings import (
    aggregate_from_sources,
    clean_bookmix_block,
    clean_fl_block,
    clean_fw_block,
    clean_kubikus_block,
    clean_ll_block,
    valid_rating,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "data" / "processed"
FW_BOOKS = ROOT / "data" / "raw" / "fw_books"
BOOKMIX_RAW = ROOT / "data" / "raw" / "bookmix"
FL_WORK = ROOT / "data" / "raw" / "fantlab_work"
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


def attach_description(entry: dict) -> None:
    if entry.get("description"):
        return

    title = entry.get("title") or ""
    candidates: list[tuple[str, str]] = []

    fw_id = (entry.get("fantasy_worlds") or {}).get("id")
    if fw_id:
        path = FW_BOOKS / f"{fw_id}.html"
        if path.exists():
            text = extract_fw_description(path.read_text(encoding="utf-8", errors="ignore"), title)
            if text:
                candidates.append(("fantasy_worlds", text))

    bm_id = (entry.get("bookmix") or {}).get("id")
    if bm_id:
        path = BOOKMIX_RAW / f"{bm_id}.html"
        if path.exists():
            text = extract_bookmix_description(path.read_text(encoding="utf-8", errors="ignore"))
            if text:
                candidates.append(("bookmix", text))

    fl_id = (entry.get("fantlab") or {}).get("id")
    if fl_id:
        path = FL_WORK / f"{fl_id}.html"
        if path.exists():
            text = extract_fantlab_description(path.read_text(encoding="utf-8", errors="ignore"))
            if text:
                candidates.append(("fantlab", text))

    if not candidates:
        return
    candidates.sort(key=lambda item: len(item[1]), reverse=True)
    source, text = candidates[0]
    entry["description"] = text
    entry["description_source"] = source


def load_source_records(path: Path, source: str) -> list[BookRecord]:
    if not path.exists():
        return []
    records: list[BookRecord] = []
    for item in json.loads(path.read_text(encoding="utf-8")):
        item = dict(item)
        item.pop("normalized_score", None)
        item.pop("lists", None)
        item["source"] = source
        record = BookRecord(**{k: v for k, v in item.items() if k in {f.name for f in fields(BookRecord)}})
        record.normalized_title = normalize_title(record.title)
        record.normalized_authors = normalize_authors(record.authors)
        records.append(record)
    return records


def entry_anchor(entry: dict) -> BookRecord:
    return BookRecord(
        source="catalog",
        external_id=entry["id"],
        title=entry["title"],
        authors=entry.get("authors", []),
        normalized_title=normalize_title(entry["title"]),
        normalized_authors=normalize_authors(entry.get("authors", [])),
    )


def match_external(entry: dict, pool: list[BookRecord], used: set[str]) -> BookRecord | None:
    candidates = [book for book in pool if book.external_id not in used]
    result = find_best_match(entry_anchor(entry), candidates, MATCH_THRESHOLD)
    if not result or not result.livelib:
        return None
    return result.livelib


def source_block(record: BookRecord) -> dict:
    return {
        "id": record.external_id,
        "rating": record.rating,
        "votes": record.vote_count,
        "url": record.url,
    }


def find_fw_catalog_match(
    title: str,
    authors: list[str],
    catalog: list[dict],
    used_fw_ids: set[str],
) -> dict | None:
    anchor = entry_anchor({"id": "probe", "title": title, "authors": authors})
    best_book: dict | None = None
    best_score = 0.0
    for book in catalog:
        book_id = str(book["id"])
        if book_id in used_fw_ids:
            continue
        candidate = BookRecord(
            source="fantasy_worlds",
            external_id=book_id,
            title=book["title"],
            authors=book.get("authors", []),
            normalized_title=normalize_title(book["title"]),
            normalized_authors=normalize_authors(book.get("authors", [])),
        )
        score = score_pair(anchor, candidate)
        if score > best_score:
            best_score = score
            best_book = book
    if best_book and best_score >= MATCH_THRESHOLD:
        return best_book
    return None


def attach_fw_download(entry: dict, fw_book: dict) -> None:
    fw_id = str(fw_book["id"])
    rating, votes, genres, fantlab_id = fw_rating(fw_book)
    entry.setdefault("fantasy_worlds", {})
    entry["fantasy_worlds"].update(
        {
            "id": fw_id,
            "rating": rating,
            "votes": votes,
            "url": fw_book.get("url") or fw.book_url(fw_id),
            "download_url": fw_book.get("download_url") or fw.download_url(fw_id),
        }
    )
    entry["download_url"] = entry["fantasy_worlds"]["download_url"]
    if genres:
        merged = list(dict.fromkeys([*(entry.get("genres") or []), *genres]))
        entry["genres"] = merged
    if fantlab_id and not entry.get("fantlab_link"):
        entry["fantlab_link"] = {"id": str(fantlab_id)}


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
    kb_info = entry.get("kubikus")
    if kb_info and kb_info.get("rating") is not None:
        sources.append(("kubikus", float(kb_info["rating"]), kb_info.get("votes")))
    bm_info = entry.get("bookmix")
    if bm_info and bm_info.get("rating") is not None:
        sources.append(("bookmix", float(bm_info["rating"]), bm_info.get("votes")))
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
    if entry.get("kubikus"):
        entry["kubikus"] = clean_kubikus_block(entry["kubikus"])
        if not entry["kubikus"]:
            entry.pop("kubikus", None)
    if entry.get("bookmix"):
        entry["bookmix"] = clean_bookmix_block(entry["bookmix"])
        if not entry["bookmix"]:
            entry.pop("bookmix", None)
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

    attach_description(entry)
    return entry


def main() -> None:
    merged = load_json(OUT / "merged_works.json")
    catalog = load_json(OUT / "fw_catalog.json")
    fl_api = load_fl_api()
    kubikus_records = load_source_records(OUT / "kubikus_books.json", "kubikus")
    bookmix_records = load_source_records(OUT / "bookmix_books.json", "bookmix")
    readrate = {item["external_id"]: item for item in load_json(OUT / "readrate_books.json")}

    used_kubikus: set[str] = set()
    used_bookmix: set[str] = set()
    used_fw_ids = {
        str(entry.get("fantasy_worlds", {}).get("id"))
        for entry in merged
        if entry.get("fantasy_worlds", {}).get("id")
    }

    expanded = []
    for entry in merged:
        row = dict(entry)
        kb_match = match_external(row, kubikus_records, used_kubikus)
        if kb_match:
            used_kubikus.add(kb_match.external_id)
            row["kubikus"] = source_block(kb_match)
            if kb_match.genres:
                row["genres"] = list(dict.fromkeys([*(row.get("genres") or []), *kb_match.genres]))
        bm_match = match_external(row, bookmix_records, used_bookmix)
        if bm_match:
            used_bookmix.add(bm_match.external_id)
            row["bookmix"] = source_block(bm_match)
            if bm_match.genres:
                row["genres"] = list(dict.fromkeys([*(row.get("genres") or []), *bm_match.genres]))
        if not row.get("download_url"):
            fw_book = find_fw_catalog_match(row["title"], row.get("authors", []), catalog, used_fw_ids)
            if fw_book:
                used_fw_ids.add(str(fw_book["id"]))
                attach_fw_download(row, fw_book)
        expanded.append(sanitize_entry(row, fl_api))

    linked_fw_ids = used_fw_ids.copy()
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

    kubikus_added = bookmix_added = 0
    for record in kubikus_records:
        if record.external_id in used_kubikus:
            continue
        fw_book = find_fw_catalog_match(record.title, record.authors, catalog, used_fw_ids)
        entry = {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"kubikus:{record.external_id}")),
            "title": record.title,
            "authors": record.authors,
            "genres": record.genres,
            "kubikus": source_block(record),
            "source_origin": "kubikus",
        }
        if fw_book:
            used_fw_ids.add(str(fw_book["id"]))
            attach_fw_download(entry, fw_book)
        entry = sanitize_entry(entry, fl_api)
        if entry.get("aggregate_rating") is not None:
            expanded.append(entry)
            kubikus_added += 1
            used_kubikus.add(record.external_id)

    for record in bookmix_records:
        if record.external_id in used_bookmix:
            continue
        if record.rating is None:
            continue
        fw_book = find_fw_catalog_match(record.title, record.authors, catalog, used_fw_ids)
        entry = {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"bookmix:{record.external_id}")),
            "title": record.title,
            "authors": record.authors,
            "genres": record.genres,
            "bookmix": source_block(record),
            "source_origin": "bookmix",
        }
        if fw_book:
            used_fw_ids.add(str(fw_book["id"]))
            attach_fw_download(entry, fw_book)
        entry = sanitize_entry(entry, fl_api)
        if entry.get("aggregate_rating") is not None or entry.get("download_url"):
            expanded.append(entry)
            bookmix_added += 1
            used_bookmix.add(record.external_id)

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
        "with_description": sum(1 for item in expanded if item.get("description")),
        "kubikus_indexed": len(kubikus_records),
        "kubikus_matched": len(used_kubikus),
        "kubikus_only_added": kubikus_added,
        "bookmix_indexed": len(bookmix_records),
        "bookmix_matched": len(used_bookmix),
        "bookmix_only_added": bookmix_added,
        "readrate_indexed": len(readrate),
        "rating_policy": "parsed sources only, min votes: fantlab=10, livelib=5, fw=10, kubikus=10, bookmix=5",
    }
    (OUT / "expanded_report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
