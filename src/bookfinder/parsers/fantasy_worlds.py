from __future__ import annotations

import json
import re
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from bookfinder.models import BookRecord
from bookfinder.normalize import normalize_authors, normalize_title

BASE_URL = "https://fantasy-worlds.net"

FANTLAB_ID_RE = re.compile(r"fantlab_id\s*=\s*(\d+)")
POLL_RE = re.compile(
    r'id="poll_mark1_(\d+)"[^>]*>Рейтинг:\s*(?:<meta[^>]+>)*\s*([\d.]+)/(\d+)',
    re.DOTALL,
)
HOME_TOP_RE = re.compile(
    r'<a href="/lib/id(\d+)/">([^<]+)</a>',
)


def book_url(book_id: str | int) -> str:
    return urljoin(BASE_URL, f"/lib/id{book_id}/")


def download_url(book_id: str | int, fmt: str = "fb2") -> str:
    suffix = "" if fmt == "fb2" else fmt
    return urljoin(BASE_URL, f"/lib/id{book_id}/download/{suffix}")


def search_url(query: str) -> str:
    return urljoin(BASE_URL, f"/search.json?q={quote(query)}")


def _author_from_search(item: dict) -> list[str]:
    name = (item.get("author_name") or "").strip()
    surname = (item.get("author_surname") or "").strip()
    full = f"{name} {surname}".strip()
    return [full] if full else []


def record_from_search_item(item: dict, rank: int | None = None) -> BookRecord | None:
    book_id = str(item.get("id") or "").strip()
    title = (item.get("title") or "").strip()
    if not book_id or not title:
        return None

    year: int | None = None
    raw_year = item.get("year")
    if raw_year:
        try:
            year = int(str(raw_year)[:4])
        except ValueError:
            year = None

    authors = _author_from_search(item)
    return BookRecord(
        source="fantasy_worlds",
        external_id=book_id,
        title=title,
        authors=authors,
        year=year,
        rank=rank,
        url=book_url(book_id),
        normalized_title=normalize_title(title),
        normalized_authors=normalize_authors(authors),
    )


def parse_search_json(raw: str | dict) -> list[BookRecord]:
    data = json.loads(raw) if isinstance(raw, str) else raw
    records: list[BookRecord] = []
    seen: set[str] = set()

    for idx, item in enumerate(data.get("books", []), start=1):
        record = record_from_search_item(item, rank=idx)
        if record is None or record.external_id in seen:
            continue
        seen.add(record.external_id)
        records.append(record)

    return records


def extract_fantlab_id(html: str) -> str | None:
    match = FANTLAB_ID_RE.search(html)
    return match.group(1) if match else None


def _rating_from_soup(soup: BeautifulSoup) -> tuple[float | None, float, int | None]:
    value_el = soup.select_one('meta[itemprop="ratingValue"]')
    count_el = soup.select_one('meta[itemprop="ratingCount"]')
    best_el = soup.select_one('meta[itemprop="bestRating"]')

    if value_el and count_el:
        try:
            rating = float(value_el.get("content", "").replace(",", "."))
            votes = int(count_el.get("content", "0"))
            rating_max = float(best_el.get("content", "10")) if best_el else 10.0
            if votes > 0:
                return rating, rating_max, votes
        except ValueError:
            pass

    poll = soup.select_one('[id^="poll_mark1_"]')
    if poll:
        text = poll.get_text(" ", strip=True)
        match = re.search(r"([\d.]+)/(\d+)", text)
        if match:
            try:
                rating = float(match.group(1))
                votes = int(match.group(2))
                if votes > 0:
                    return rating, 10.0, votes
            except ValueError:
                pass

    return None, 10.0, None


def parse_book_page(html: str) -> BookRecord | None:
    soup = BeautifulSoup(html, "lxml")

    book_id: str | None = None
    poll_el = soup.select_one('[id^="poll_mark1_"]')
    if poll_el and poll_el.get("id", "").startswith("poll_mark1_"):
        book_id = poll_el["id"].replace("poll_mark1_", "")

    if not book_id:
        download = soup.select_one('a[id^="download_book_"]')
        if download and download.get("id", "").startswith("download_book_"):
            book_id = download["id"].replace("download_book_", "")

    title_el = soup.select_one('span[itemprop="name"]')
    if not title_el:
        h1 = soup.select_one("h1")
        title_el = h1
    title = title_el.get_text(strip=True) if title_el else ""
    if not title:
        return None

    authors = [a.get_text(strip=True) for a in soup.select('a[itemprop="author"]') if a.get_text(strip=True)]
    if not authors:
        author_link = soup.select_one('p a[href*="/author/id"]')
        if author_link:
            authors = [author_link.get_text(strip=True)]

    rating, rating_max, votes = _rating_from_soup(soup)
    genres = [a.get_text(strip=True) for a in soup.select('a[href*="/lib/tag"]') if a.get_text(strip=True)]

    year: int | None = None
    for p in soup.select("p"):
        text = p.get_text(" ", strip=True)
        if text.startswith("Год:"):
            match = re.search(r"\b(19|20)\d{2}\b", text)
            if match:
                year = int(match.group(0))
            break

    if not book_id:
        match = re.search(r"/lib/id(\d+)/", html)
        book_id = match.group(1) if match else ""

    return BookRecord(
        source="fantasy_worlds",
        external_id=book_id,
        title=title,
        authors=authors,
        rating=rating,
        rating_max=rating_max,
        vote_count=votes,
        year=year,
        url=book_url(book_id) if book_id else None,
        genres=genres,
        normalized_title=normalize_title(title),
        normalized_authors=normalize_authors(authors),
    )


def parse_home_top(html: str, limit: int = 100) -> list[BookRecord]:
    records: list[BookRecord] = []
    seen: set[str] = set()

    for match in HOME_TOP_RE.finditer(html):
        book_id = match.group(1)
        if book_id in seen:
            continue
        seen.add(book_id)

        label = BeautifulSoup(match.group(2), "lxml").get_text(strip=True)
        authors: list[str] = []
        title = label
        if " - " in label:
            author_part, title_part = label.split(" - ", 1)
            authors = [author_part.strip()]
            title = title_part.strip()
        elif " — " in label:
            author_part, title_part = label.split(" — ", 1)
            authors = [author_part.strip()]
            title = title_part.strip()

        records.append(
            BookRecord(
                source="fantasy_worlds",
                external_id=book_id,
                title=title,
                authors=authors,
                rank=len(records) + 1,
                url=book_url(book_id),
                normalized_title=normalize_title(title),
                normalized_authors=normalize_authors(authors),
            )
        )
        if len(records) >= limit:
            break

    return records
