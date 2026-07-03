from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from bookfinder.models import BookRecord
from bookfinder.normalize import normalize_authors, normalize_title

BASE_URL = "https://fantlab.ru"

WORK_TYPE_LABELS = {
    1: "роман",
    2: "повесть",
    3: "рассказ",
    4: "цикл",
}

RATING_ROW_RE = re.compile(
    r"<tr[^>]*valign=top[^>]*>.*?hide-on-mobile'>(\d+)</td>.*?<span[^>]*>"
    r"(.+?)\.\s*<a[^>]+href=\"(/work\d+)\">([^<]+)</a>.*?</span>.*?"
    r"<nobr>([\d.]+)\s*\((\d+)\)</nobr>",
    re.DOTALL,
)

INSUFFICIENT_VOTES_MARKER = "недостаточным количеством оценок"

WORK_META_RE = re.compile(
    r"Средняя\s+оценка:\s*([\d.,]+)\s*Оценок:\s*(\d+)",
    re.IGNORECASE,
)


def _trim_rating_html(html: str) -> str:
    idx = html.find(INSUFFICIENT_VOTES_MARKER)
    if idx != -1:
        return html[:idx]
    return html


def _extract_authors(row_html: str) -> list[str]:
    span_match = re.search(r"<span[^>]*>(.*?)</span>", row_html, re.DOTALL)
    if not span_match:
        return []

    inner = span_match.group(1)
    author_match = re.search(r"^(.+?)\.\s*<a\s", inner.strip(), re.DOTALL)
    if not author_match:
        return []

    return [part.strip() for part in re.split(r",\s*", author_match.group(1)) if part.strip()]


def parse_rating_page(html: str, work_type: int = 1) -> list[BookRecord]:
    html = _trim_rating_html(html)
    records: list[BookRecord] = []
    seen: set[str] = set()

    for match in RATING_ROW_RE.finditer(html):
        rank = int(match.group(1))
        if rank > 100:
            continue
        authors_raw = match.group(2)
        work_path = match.group(3)
        title = BeautifulSoup(match.group(4), "lxml").get_text(strip=True)
        rating = float(match.group(5))
        votes = int(match.group(6))
        work_id = work_path.replace("/work", "")

        if work_id in seen:
            continue
        seen.add(work_id)

        authors = [part.strip() for part in re.split(r",\s*", authors_raw) if part.strip()]

        row_context = html[max(0, match.start() - 50) : match.end() + 50]
        year: int | None = None
        year_match = re.search(r",\s*(\d{4})\s*г\.", row_context)
        if year_match:
            year = int(year_match.group(1))

        record = BookRecord(
            source="fantlab",
            external_id=work_id,
            title=title,
            authors=authors,
            rating=rating,
            rating_max=10.0,
            vote_count=votes,
            rank=rank,
            work_type=WORK_TYPE_LABELS.get(work_type),
            year=year,
            url=urljoin(BASE_URL, work_path),
            normalized_title=normalize_title(title),
            normalized_authors=normalize_authors(authors),
        )
        records.append(record)

    records.sort(key=lambda r: (r.rank or 9999, r.external_id))
    return records[:100]


def parse_work_meta(html: str, work_id: str) -> dict:
    """Rating, title and genres from FantLab work HTML (API fallback)."""
    soup = BeautifulSoup(html, "lxml")
    rating_val: float | None = None
    votes: int | None = None

    match = WORK_META_RE.search(html)
    if match:
        rating_val = float(match.group(1).replace(",", "."))
        votes = int(match.group(2))

    title: str | None = None
    for selector in ("h1", "h2"):
        node = soup.select_one(selector)
        if not node:
            continue
        text = node.get_text(" ", strip=True)
        quoted = re.search(r"«([^»]+)»", text)
        title = quoted.group(1) if quoted else text
        break

    return {
        "work_id": work_id,
        "work_name": title,
        "rating": {
            "rating": str(rating_val) if rating_val is not None else None,
            "voters": votes,
        },
        "genres": parse_work_page(html, work_id),
        "source": "html",
    }


def parse_work_page(html: str, work_id: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    genres: list[str] = []

    for node in soup.find_all(string=re.compile(r"Жанр", re.I)):
        parent = node.parent
        if parent is None:
            continue
        block = parent.find_parent("tr") or parent.find_parent("div") or parent
        for link in block.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)
            if "/genre" in href or "/bygenre" in href:
                if text and text not in genres:
                    genres.append(text)

    if not genres:
        for link in soup.select('a[href*="/genre"]'):
            text = link.get_text(strip=True)
            if text and text not in genres:
                genres.append(text)

    return genres[:15]


def rating_url(work_type: int, threshold: int = 250) -> str:
    return f"{BASE_URL}/rating/work/best?type={work_type}&threshold={threshold}"


def work_url(work_id: str) -> str:
    return f"{BASE_URL}/work{work_id}"
