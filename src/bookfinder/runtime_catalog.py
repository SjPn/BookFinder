"""Compact runtime catalog files for low-memory deployment."""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from pathlib import Path

INDEX_FIELDS = (
    "id",
    "title",
    "authors",
    "genres",
    "year",
    "aggregate_rating",
    "source_origin",
    "download_url",
    "fb2_local",
    "fantlab",
    "livelib",
    "fantasy_worlds",
    "kubikus",
    "bookmix",
    "loveread",
)

_TOKEN_SPLIT = re.compile(r"[\s+.,;:!?\-\"«»()\[\]/]+")
TOKEN_DB_NAME = "works_tokens.db"


def normalize_search_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("+", " ")
    return re.sub(r"\s+", " ", text).strip().casefold()


def word_stem(word: str) -> str:
    word = word.strip().lower()
    if len(word) <= 4:
        return word
    if len(word) >= 7:
        return word[:-2]
    return word[:-1]


def index_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for word in _TOKEN_SPLIT.split(normalize_search_text(text)):
        if len(word) < 2:
            continue
        tokens.add(word)
        stem = word_stem(word)
        if stem and len(stem) >= 4:
            tokens.add(stem)
    return tokens


def work_search_blob(work: dict) -> str:
    return " ".join(
        [
            work.get("title", ""),
            " ".join(work.get("authors", [])),
            " ".join(work.get("genres", [])),
        ]
    )


def build_index_entry(work: dict) -> dict:
    entry = {key: work[key] for key in INDEX_FIELDS if key in work}
    entry["search_blurb"] = (work.get("description") or "")[:300]
    return entry


def build_token_db(works: list[dict], db_path: Path) -> int:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute(
        """
        CREATE TABLE token_hits (
            token TEXT NOT NULL,
            rowid INTEGER NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX idx_token_hits_token ON token_hits(token)")
    batch: list[tuple[str, int]] = []
    for rowid, work in enumerate(works):
        for token in index_tokens(work_search_blob(work)):
            batch.append((token, rowid))
        if len(batch) >= 50000:
            conn.executemany("INSERT INTO token_hits(token, rowid) VALUES (?, ?)", batch)
            batch.clear()
    if batch:
        conn.executemany("INSERT INTO token_hits(token, rowid) VALUES (?, ?)", batch)
    conn.commit()
    token_count = conn.execute("SELECT COUNT(*) FROM token_hits").fetchone()[0]
    conn.close()
    return int(token_count)


def write_runtime_catalog(works: list[dict], out_dir: Path) -> dict:
    index = [build_index_entry(work) for work in works]
    index.sort(
        key=lambda item: (-(item.get("aggregate_rating") or 0), item.get("title", "").casefold()),
    )
    details: dict[str, dict] = {}
    genre_counts: dict[str, int] = {}

    for work in works:
        work_id = work["id"]
        if work.get("description"):
            details[work_id] = {
                "description": work["description"],
                "description_source": work.get("description_source"),
            }
        for genre in work.get("genres", []):
            if genre:
                genre_counts[genre] = genre_counts.get(genre, 0) + 1

    dump = lambda payload: json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "works_index.json").write_text(dump(index), encoding="utf-8")
    (out_dir / "works_details.json").write_text(dump(details), encoding="utf-8")

    total = len(index) or 1
    genres = [
        {
            "name": name,
            "count": count,
            "weight": round(count / total, 4),
        }
        for name, count in sorted(genre_counts.items(), key=lambda item: item[0].casefold())
    ]
    (out_dir / "genres.json").write_text(dump(genres), encoding="utf-8")
    token_rows = build_token_db(index, out_dir / TOKEN_DB_NAME)

    return {
        "index_bytes": (out_dir / "works_index.json").stat().st_size,
        "details_bytes": (out_dir / "works_details.json").stat().st_size,
        "genres_bytes": (out_dir / "genres.json").stat().st_size,
        "token_db_bytes": (out_dir / TOKEN_DB_NAME).stat().st_size,
        "token_rows": token_rows,
        "works": len(index),
        "with_description": len(details),
        "genres": len(genres),
    }
