from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from bookfinder.catalog import genre_counts, load_works, reload_works, search_works, similar_works
from bookfinder.parsers import fantasy_worlds as fw

app = FastAPI(title="Bookfinder", version="0.1.0")

WEB = Path(__file__).resolve().parents[2] / "web"
DATA = Path(__file__).resolve().parents[2] / "data"
FB2_DIR = DATA / "books" / "fb2"
WEB.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.get("/api/stats")
def stats() -> dict:
    works = load_works()
    report_path = Path(__file__).resolve().parents[2] / "data" / "processed" / "merge_report.json"
    report = {}
    if report_path.exists():
        import json

        report = json.loads(report_path.read_text(encoding="utf-8"))
    genres: set[str] = set()
    for w in works:
        genres.update(w.get("genres", []))
    return {
        "works_count": len(works),
        "genres_count": len(genres),
        "merge": report,
    }


@app.get("/api/top")
def top(
    limit: int = Query(100, ge=1, le=500),
    genre: str | None = None,
    subgenre: str | None = None,
    q: str | None = None,
    match: str = Query("any", pattern="^(any|all)$"),
) -> list[dict]:
    selected = [g for g in [subgenre, genre] if g and g.strip()]
    result = search_works(query=q or "", genres=selected, match=match, limit=limit)
    return result["items"]


@app.get("/api/search")
def search(
    q: str = "",
    genres: list[str] = Query(default=[]),
    match: str = Query("any", pattern="^(any|all)$"),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    return search_works(query=q, genres=genres, match=match, limit=limit)


@app.get("/api/genres")
def genres() -> list[dict]:
    return genre_counts()


@app.get("/api/works/{work_id}")
def work_detail(work_id: str) -> dict:
    for w in load_works():
        if w["id"] == work_id:
            return w
    return {"error": "not found"}


@app.get("/api/works/{work_id}/similar")
def work_similar(work_id: str, limit: int = Query(12, ge=1, le=50)) -> list[dict]:
    return similar_works(work_id, limit)


@app.get("/api/download/fw/{book_id}", response_model=None)
def download_fw(book_id: str) -> Response:
    local = FB2_DIR / f"{book_id}.fb2.zip"
    if local.exists():
        return FileResponse(local, filename=local.name, media_type="application/zip")
    return RedirectResponse(fw.download_url(book_id))


@app.post("/api/reload")
def api_reload() -> dict:
    works = reload_works()
    return {"works_count": len(works)}
