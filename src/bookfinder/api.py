from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from bookfinder.catalog import genre_counts, get_work, reload_works, search_works, similar_works, works_count
from bookfinder.dna_similarity import DNA_MODES
from bookfinder.dna_service import dna_available, get_dna_public, similar_works_dna
from bookfinder.parsers import fantasy_worlds as fw
from bookfinder.reviews_store import get_reviews_for_work
from bookfinder.user_ratings import delete_user_rating, get_user_rating, set_user_rating, work_user_stats

app = FastAPI(title="Bookfinder", version="0.1.0")

WEB = Path(__file__).resolve().parents[2] / "web"
DATA = Path(__file__).resolve().parents[2] / "data"
FB2_DIR = DATA / "books" / "fb2"
NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}
WEB.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html", headers=NO_CACHE)


@app.get("/work/{work_id}")
def work_page(work_id: str) -> FileResponse:
    del work_id  # HTML page reads id from URL in book.js
    return FileResponse(WEB / "book.html", headers=NO_CACHE)


@app.get("/api/stats")
async def stats() -> dict:
    report_path = Path(__file__).resolve().parents[2] / "data" / "processed" / "merge_report.json"
    report = {}
    if report_path.exists():
        import json

        report = json.loads(report_path.read_text(encoding="utf-8"))
    return {
        "works_count": works_count(),
        "genres_count": len(genre_counts()),
        "merge": report,
    }


@app.get("/api/top")
async def top(
    limit: int = Query(100, ge=1, le=500),
    genre: str | None = None,
    subgenre: str | None = None,
    q: str | None = None,
    match: str = Query("any", pattern="^(any|all)$"),
) -> list[dict]:
    selected = [g for g in [subgenre, genre] if g and g.strip()]
    result = await run_in_threadpool(
        search_works,
        query=q or "",
        genres=selected,
        match=match,
        limit=limit,
    )
    return result["items"]


@app.get("/api/search")
async def search(
    q: str = "",
    genres: list[str] = Query(default=[]),
    match: str = Query("any", pattern="^(any|all)$"),
    limit: int = Query(200, ge=1, le=1000),
) -> dict:
    return await run_in_threadpool(search_works, query=q, genres=genres, match=match, limit=limit)


@app.get("/api/genres")
async def genres() -> list[dict]:
    return genre_counts()


@app.get("/api/works/{work_id}")
async def work_detail(work_id: str) -> dict:
    work = await run_in_threadpool(get_work, work_id)
    if work:
        return work
    return {"error": "not found"}


@app.get("/api/works/{work_id}/similar")
async def work_similar(
    work_id: str,
    limit: int = Query(12, ge=1, le=50),
    mode: str = Query("auto"),
) -> list[dict]:
    selected_mode = mode.strip().casefold()
    if selected_mode == "legacy":
        return await run_in_threadpool(similar_works, work_id, limit)

    use_dna = selected_mode in DNA_MODES or selected_mode == "auto"
    if use_dna and dna_available():
        dna_mode = "ideas" if selected_mode == "auto" else selected_mode
        dna_items = await run_in_threadpool(similar_works_dna, work_id, mode=dna_mode, limit=limit)
        if dna_items:
            return dna_items
        if selected_mode != "auto":
            # Explicit DNA mode requested but no neighbors/profiles yet — fall back.
            return await run_in_threadpool(similar_works, work_id, limit)
        return await run_in_threadpool(similar_works, work_id, limit)

    return await run_in_threadpool(similar_works, work_id, limit)


@app.get("/api/works/{work_id}/dna")
async def work_dna(work_id: str) -> dict:
    payload = await run_in_threadpool(get_dna_public, work_id)
    if payload:
        return payload
    return {"error": "not found", "work_id": work_id}


@app.get("/api/dna/modes")
async def dna_modes() -> dict:
    return {"modes": list(DNA_MODES), "available": dna_available()}


@app.get("/api/works/{work_id}/reviews")
async def work_reviews(work_id: str, limit: int = Query(15, ge=1, le=30)) -> dict:
    from bookfinder.catalog_db import CatalogStore

    store = CatalogStore(DATA)
    fw_id = store.get_work_fw_id(work_id) if store.available() else None
    if fw_id is None:
        work = await run_in_threadpool(get_work, work_id)
        if work:
            fw_id = (work.get("fantasy_worlds") or {}).get("id")
    return await run_in_threadpool(
        get_reviews_for_work,
        work_id,
        limit,
        str(fw_id) if fw_id else None,
    )


class UserRatingBody(BaseModel):
    user_id: str = Field(min_length=8, max_length=64)
    rating: int = Field(ge=1, le=10)


@app.get("/api/works/{work_id}/user-rating")
def read_user_rating(work_id: str, user_id: str = Query(..., min_length=8, max_length=64)) -> dict:
    rating = get_user_rating(user_id, work_id)
    return {
        "work_id": work_id,
        "user_id": user_id,
        "rating": rating,
        "community": work_user_stats(work_id),
    }


@app.put("/api/works/{work_id}/user-rating")
def write_user_rating(work_id: str, body: UserRatingBody) -> dict:
    saved = set_user_rating(body.user_id, work_id, body.rating)
    return {**saved, "community": work_user_stats(work_id)}


@app.delete("/api/works/{work_id}/user-rating")
def remove_user_rating(work_id: str, user_id: str = Query(..., min_length=8, max_length=64)) -> dict:
    deleted = delete_user_rating(user_id, work_id)
    return {"deleted": deleted, "community": work_user_stats(work_id)}


@app.get("/api/download/fw/{book_id}", response_model=None)
def download_fw(book_id: str) -> Response:
    local = FB2_DIR / f"{book_id}.fb2.zip"
    if local.exists():
        return FileResponse(local, filename=local.name, media_type="application/zip")
    return RedirectResponse(fw.download_url(book_id))


@app.post("/api/reload")
def api_reload() -> dict:
    count = reload_works()
    return {"works_count": count}
