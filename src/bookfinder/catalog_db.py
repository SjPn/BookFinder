"""SQLite runtime catalog: one row per work, indexed search, no full JSON in RAM."""

from __future__ import annotations

import gzip
import json
import shutil
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

from bookfinder.genre_filter import is_catalog_genre
from bookfinder.runtime_catalog import index_tokens, work_search_blob

CATALOG_DB_NAME = "catalog.db"
SCHEMA_VERSION = 1
_SOURCE_JSON_FIELDS = (
    "fantlab",
    "livelib",
    "fantasy_worlds",
    "kubikus",
    "bookmix",
    "loveread",
)
_BATCH = 400
_IN_CHUNK = 450


def ensure_catalog_db(data_dir: Path) -> Path:
    """Decompress catalog.db.gz when catalog.db is missing (deploy / fresh clone)."""
    db_path = data_dir / CATALOG_DB_NAME
    if db_path.exists():
        return db_path
    gzip_path = data_dir / f"{CATALOG_DB_NAME}.gz"
    if not gzip_path.exists():
        return db_path
    with gzip.open(gzip_path, "rb") as src, db_path.open("wb") as dst:
        shutil.copyfileobj(src, dst)
    return db_path


def _json_loads(value: str | None) -> Any:
    if not value:
        return None
    return json.loads(value)


def _row_to_work(row: sqlite3.Row, *, include_description: bool = True) -> dict:
    work: dict[str, Any] = {
        "id": row["id"],
        "title": row["title"],
        "authors": _json_loads(row["authors_json"]) or [],
        "genres": _json_loads(row["genres_json"]) or [],
        "year": row["year"],
        "aggregate_rating": row["aggregate_rating"],
        "source_origin": row["source_origin"],
        "download_url": row["download_url"],
        "fb2_local": bool(row["fb2_local"]),
        "search_blurb": row["search_blurb"] or "",
    }
    for field in _SOURCE_JSON_FIELDS:
        value = _json_loads(row[f"{field}_json"])
        if value is not None:
            work[field] = value
    if include_description:
        if row["description"]:
            work["description"] = row["description"]
        if row["description_source"]:
            work["description_source"] = row["description_source"]
    return work


class CatalogStore:
    """Thread-local read-only SQLite connections (safe under FastAPI thread pool)."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._path = data_dir / CATALOG_DB_NAME
        self._local = threading.local()

    def available(self) -> bool:
        ensure_catalog_db(self._data_dir)
        return self._path.exists()

    def path(self) -> Path:
        return self._path

    def close_thread(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                f"file:{self._path.as_posix()}?mode=ro",
                uri=True,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            conn.execute("PRAGMA cache_size=-16000")
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.execute("PRAGMA mmap_size=268435456")
            self._local.conn = conn
        return conn

    def count_works(self) -> int:
        row = self._connect().execute("SELECT COUNT(*) AS c FROM works").fetchone()
        return int(row["c"])

    def get_work(self, work_id: str) -> dict | None:
        row = self._connect().execute(
            "SELECT * FROM works WHERE id = ?",
            (work_id,),
        ).fetchone()
        if row is None:
            return None
        work = _row_to_work(row, include_description=True)
        work.pop("search_blurb", None)
        return work

    def get_work_fw_id(self, work_id: str) -> str | None:
        row = self._connect().execute(
            "SELECT fantasy_worlds_json FROM works WHERE id = ?",
            (work_id,),
        ).fetchone()
        if row is None:
            return None
        payload = _json_loads(row["fantasy_worlds_json"])
        if isinstance(payload, dict) and payload.get("id"):
            return str(payload["id"])
        return None

    def top_works(self, limit: int) -> list[dict]:
        rows = self._connect().execute(
            """
            SELECT * FROM works
            ORDER BY aggregate_rating DESC, title COLLATE NOCASE
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_row_to_work(row, include_description=False) for row in rows]

    def get_works_by_rowids(self, rowids: Iterable[int]) -> list[dict]:
        ids = [int(rowid) for rowid in rowids]
        if not ids:
            return []
        conn = self._connect()
        works: list[dict] = []
        for offset in range(0, len(ids), _IN_CHUNK):
            chunk = ids[offset : offset + _IN_CHUNK]
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"SELECT * FROM works WHERE rowid IN ({placeholders})",
                chunk,
            ).fetchall()
            works.extend(_row_to_work(row, include_description=False) for row in rows)
        return works

    def get_works_by_ids(self, work_ids: Iterable[str]) -> list[dict]:
        ids = [work_id for work_id in work_ids]
        if not ids:
            return []
        conn = self._connect()
        works: list[dict] = []
        for offset in range(0, len(ids), _IN_CHUNK):
            chunk = ids[offset : offset + _IN_CHUNK]
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"SELECT * FROM works WHERE id IN ({placeholders})",
                chunk,
            ).fetchall()
            works.extend(_row_to_work(row, include_description=False) for row in rows)
        return works

    def list_genres(self) -> list[dict]:
        rows = self._connect().execute(
            "SELECT name, count, weight FROM catalog_genres ORDER BY name COLLATE NOCASE",
        ).fetchall()
        return [{"name": row["name"], "count": row["count"], "weight": row["weight"]} for row in rows]

    def genre_catalog_counts(self) -> dict[str, int]:
        rows = self._connect().execute("SELECT name, count FROM catalog_genres").fetchall()
        return {row["name"]: int(row["count"]) for row in rows}

    def lookup_tokens(self, token: str) -> tuple[int, ...]:
        rows = self._connect().execute(
            "SELECT work_rowid FROM token_hits WHERE token = ?",
            (token,),
        ).fetchall()
        return tuple(int(row["work_rowid"]) for row in rows)

    def rowids_for_genre_lower(self, genre_lower: str) -> frozenset[int]:
        rows = self._connect().execute(
            "SELECT work_rowid FROM genre_works WHERE genre_lower = ?",
            (genre_lower,),
        ).fetchall()
        return frozenset(int(row["work_rowid"]) for row in rows)

    def rowids_for_genre_substring(self, needle: str) -> frozenset[int]:
        rows = self._connect().execute(
            """
            SELECT DISTINCT work_rowid FROM genre_works
            WHERE genre_lower LIKE '%' || ? || '%' OR ? LIKE '%' || genre_lower || '%'
            """,
            (needle, needle),
        ).fetchall()
        return frozenset(int(row["work_rowid"]) for row in rows)

    def genre_names(self) -> list[str]:
        rows = self._connect().execute("SELECT name FROM catalog_genres").fetchall()
        return [row["name"] for row in rows]

    def list_work_ids(self, *, limit: int = 0, only_fb2: bool = False) -> list[str]:
        query = """
            SELECT id FROM works
        """
        params: list[object] = []
        if only_fb2:
            query += " WHERE fb2_local = 1"
        query += " ORDER BY aggregate_rating DESC, title COLLATE NOCASE"
        if limit > 0:
            query += " LIMIT ?"
            params.append(limit)
        rows = self._connect().execute(query, params).fetchall()
        return [str(row["id"]) for row in rows]

    def list_work_ids_prefer_sources(self, *, limit: int = 0) -> list[str]:
        """Prefer books with annotation or local FB2 so DNA has something to analyze."""
        query = """
            SELECT id,
                   CASE
                     WHEN length(trim(coalesce(description, ''))) >= 120 THEN 0
                     WHEN fb2_local = 1 THEN 1
                     ELSE 2
                   END AS source_rank
            FROM works
            ORDER BY source_rank ASC, aggregate_rating DESC, title COLLATE NOCASE
        """
        params: list[object] = []
        if limit > 0:
            query += " LIMIT ?"
            params.append(limit)
        rows = self._connect().execute(query, params).fetchall()
        return [str(row["id"]) for row in rows]

    def similar_candidate_ids(
        self,
        work_id: str,
        genre_lowers: set[str],
        author_lowers: set[str],
    ) -> set[str]:
        conn = self._connect()
        row = conn.execute("SELECT rowid FROM works WHERE id = ?", (work_id,)).fetchone()
        if row is None:
            return set()
        exclude_rowid = int(row["rowid"])
        found: set[str] = set()

        if genre_lowers:
            placeholders = ",".join("?" for _ in genre_lowers)
            rows = conn.execute(
                f"""
                SELECT DISTINCT w.id FROM works w
                JOIN genre_works gw ON gw.work_rowid = w.rowid
                WHERE gw.genre_lower IN ({placeholders}) AND w.rowid != ?
                """,
                (*genre_lowers, exclude_rowid),
            ).fetchall()
            found.update(row["id"] for row in rows)

        if author_lowers:
            placeholders = ",".join("?" for _ in author_lowers)
            rows = conn.execute(
                f"""
                SELECT DISTINCT w.id FROM works w
                JOIN author_works aw ON aw.work_rowid = w.rowid
                WHERE aw.author_lower IN ({placeholders}) AND w.rowid != ?
                """,
                (*author_lowers, exclude_rowid),
            ).fetchall()
            found.update(row["id"] for row in rows)

        found.discard(work_id)
        return found


def build_catalog_db(works: list[dict], out_dir: Path) -> dict[str, Any]:
    """Build catalog.db from expanded works (offline, not used at request time)."""
    from bookfinder.runtime_catalog import build_index_entry

    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / CATALOG_DB_NAME
    if db_path.exists():
        db_path.unlink()

    index = [build_index_entry(work) for work in works]
    index.sort(
        key=lambda item: (-(item.get("aggregate_rating") or 0), item.get("title", "").casefold()),
    )

    genre_counts: dict[str, int] = {}
    for work in index:
        for genre in work.get("genres", []):
            if genre:
                genre_counts[genre] = genre_counts.get(genre, 0) + 1

    for i, work in enumerate(index):
        index[i] = {
            **work,
            "genres": [g for g in work.get("genres", []) if is_catalog_genre(g, genre_counts.get(g, 0))],
        }

    filtered_counts = {
        name: count for name, count in genre_counts.items() if is_catalog_genre(name, count)
    }
    total = len(index) or 1

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(
        """
        CREATE TABLE catalog_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE works (
            rowid INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            authors_json TEXT NOT NULL,
            genres_json TEXT NOT NULL,
            year INTEGER,
            aggregate_rating REAL,
            source_origin TEXT,
            download_url TEXT,
            fb2_local INTEGER NOT NULL DEFAULT 0,
            search_blurb TEXT,
            description TEXT,
            description_source TEXT,
            fantlab_json TEXT,
            livelib_json TEXT,
            fantasy_worlds_json TEXT,
            kubikus_json TEXT,
            bookmix_json TEXT,
            loveread_json TEXT
        );
        CREATE INDEX idx_works_rating ON works(aggregate_rating DESC, title COLLATE NOCASE);
        CREATE TABLE token_hits (
            token TEXT NOT NULL,
            work_rowid INTEGER NOT NULL
        );
        CREATE INDEX idx_token_hits_token ON token_hits(token);
        CREATE TABLE genre_works (
            genre_lower TEXT NOT NULL,
            genre_name TEXT NOT NULL,
            work_rowid INTEGER NOT NULL,
            PRIMARY KEY (genre_lower, work_rowid)
        );
        CREATE INDEX idx_genre_works_lower ON genre_works(genre_lower);
        CREATE TABLE author_works (
            author_lower TEXT NOT NULL,
            work_rowid INTEGER NOT NULL,
            PRIMARY KEY (author_lower, work_rowid)
        );
        CREATE INDEX idx_author_works_lower ON author_works(author_lower);
        CREATE TABLE catalog_genres (
            name TEXT PRIMARY KEY,
            count INTEGER NOT NULL,
            weight REAL NOT NULL
        );
        """
    )

    source_by_id = {work["id"]: work for work in works}
    work_rows: list[tuple] = []
    token_batch: list[tuple[str, int]] = []
    genre_batch: list[tuple[str, str, int]] = []
    author_batch: list[tuple[str, int]] = []
    descriptions = 0

    for work in index:
        work_id = work["id"]
        source = source_by_id.get(work_id, {})
        description = source.get("description") or ""
        if description:
            descriptions += 1
        source_payload = {
            field: json.dumps(work[field], ensure_ascii=False)
            for field in _SOURCE_JSON_FIELDS
            if work.get(field) is not None
        }
        work_rows.append(
            (
                work_id,
                work.get("title") or "",
                json.dumps(work.get("authors") or [], ensure_ascii=False),
                json.dumps(work.get("genres") or [], ensure_ascii=False),
                work.get("year"),
                work.get("aggregate_rating"),
                work.get("source_origin"),
                work.get("download_url"),
                1 if work.get("fb2_local") else 0,
                work.get("search_blurb") or "",
                description or None,
                source.get("description_source"),
                source_payload.get("fantlab"),
                source_payload.get("livelib"),
                source_payload.get("fantasy_worlds"),
                source_payload.get("kubikus"),
                source_payload.get("bookmix"),
                source_payload.get("loveread"),
            )
        )

    conn.executemany(
        """
        INSERT INTO works (
            id, title, authors_json, genres_json, year, aggregate_rating,
            source_origin, download_url, fb2_local, search_blurb,
            description, description_source,
            fantlab_json, livelib_json, fantasy_worlds_json,
            kubikus_json, bookmix_json, loveread_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        work_rows,
    )

    id_to_rowid = {
        row[1]: int(row[0])
        for row in conn.execute("SELECT rowid, id FROM works").fetchall()
    }

    for work in index:
        rowid = id_to_rowid[work["id"]]
        for token in index_tokens(work_search_blob(work)):
            token_batch.append((token, rowid))
        if len(token_batch) >= 50000:
            conn.executemany("INSERT INTO token_hits(token, work_rowid) VALUES (?, ?)", token_batch)
            token_batch.clear()

        for genre in work.get("genres", []):
            if genre:
                genre_batch.append((genre.casefold(), genre, rowid))
        if len(genre_batch) >= 50000:
            conn.executemany(
                "INSERT OR IGNORE INTO genre_works(genre_lower, genre_name, work_rowid) VALUES (?, ?, ?)",
                genre_batch,
            )
            genre_batch.clear()

        for author in work.get("authors", []):
            if author:
                author_batch.append((author.casefold(), rowid))
        if len(author_batch) >= 50000:
            conn.executemany(
                "INSERT OR IGNORE INTO author_works(author_lower, work_rowid) VALUES (?, ?)",
                author_batch,
            )
            author_batch.clear()

    if token_batch:
        conn.executemany("INSERT INTO token_hits(token, work_rowid) VALUES (?, ?)", token_batch)
    if genre_batch:
        conn.executemany(
            "INSERT OR IGNORE INTO genre_works(genre_lower, genre_name, work_rowid) VALUES (?, ?, ?)",
            genre_batch,
        )
    if author_batch:
        conn.executemany(
            "INSERT OR IGNORE INTO author_works(author_lower, work_rowid) VALUES (?, ?)",
            author_batch,
        )

    genre_rows = [
        (name, count, round(count / total, 4))
        for name, count in sorted(filtered_counts.items(), key=lambda item: item[0].casefold())
    ]
    conn.executemany(
        "INSERT INTO catalog_genres(name, count, weight) VALUES (?, ?, ?)",
        genre_rows,
    )
    conn.executemany(
        "INSERT INTO catalog_meta(key, value) VALUES (?, ?)",
        [
            ("schema_version", str(SCHEMA_VERSION)),
            ("works_count", str(len(index))),
            ("with_description", str(descriptions)),
        ],
    )

    token_count = conn.execute("SELECT COUNT(*) FROM token_hits").fetchone()[0]
    conn.commit()
    conn.close()

    gzip_path = db_path.with_suffix(".db.gz")
    import gzip

    with db_path.open("rb") as src, gzip.open(gzip_path, "wb", compresslevel=9) as dst:
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            dst.write(chunk)

    return {
        "catalog_db_bytes": db_path.stat().st_size,
        "catalog_db_gz_bytes": gzip_path.stat().st_size,
        "token_rows": int(token_count),
        "works": len(index),
        "with_description": descriptions,
        "genres": len(genre_rows),
        "genres_raw": len(genre_counts),
        "genres_dropped": len(genre_counts) - len(filtered_counts),
    }
