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

from bookfinder.genre_filter import is_catalog_genre

TOKEN_DB_NAME = "works_tokens.db"
_TOKEN_SPLIT = re.compile(r"[\s+.,;:!?\-\"«»()\[\]/]+")


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
    from bookfinder.catalog_db import CATALOG_DB_NAME, CatalogStore, build_catalog_db

    out_dir.mkdir(parents=True, exist_ok=True)
    summary = build_catalog_db(works, out_dir)

    # Small JSON files for tooling / fallback genre list
    genres = CatalogStore(out_dir).list_genres() if (out_dir / CATALOG_DB_NAME).exists() else []
    if not genres:
        genre_counts: dict[str, int] = {}
        for work in works:
            for genre in work.get("genres", []):
                if genre:
                    genre_counts[genre] = genre_counts.get(genre, 0) + 1
        total = len(works) or 1
        genres = [
            {
                "name": name,
                "count": count,
                "weight": round(count / total, 4),
            }
            for name, count in sorted(genre_counts.items(), key=lambda item: item[0].casefold())
            if is_catalog_genre(name, count)
        ]

    dump = lambda payload: json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    (out_dir / "genres.json").write_text(dump(genres), encoding="utf-8")
    summary["genres_bytes"] = (out_dir / "genres.json").stat().st_size
    return summary
