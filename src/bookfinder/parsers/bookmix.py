from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from bookfinder.models import BookRecord
from bookfinder.normalize import normalize_authors, normalize_title

BASE_URL = "https://bookmix.ru/"

BOOK_ID_RE = re.compile(r"[?&]id=(\d+)", re.I)
READERS_RE = re.compile(r"Читали:\s*(\d+)", re.I)
JSON_LD_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.I | re.S)


def book_url(book_id: str | int) -> str:
    return urljoin(BASE_URL, f"book.phtml?id={book_id}")


def _extract_id(href: str) -> str | None:
    match = BOOK_ID_RE.search(href)
    return match.group(1) if match else None


def _json_ld(html: str) -> dict | None:
    for block in JSON_LD_RE.findall(html):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") in {"Book", "Product"}:
            return data
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("@type") in {"Book", "Product"}:
                    return item
    return None


def parse_list_page(html: str) -> list[BookRecord]:
    soup = BeautifulSoup(html, "lxml")
    records: list[BookRecord] = []
    seen: set[str] = set()
    rank = 0

    for link in soup.select('a[href*="book.phtml?id="]'):
        href = link.get("href", "")
        book_id = _extract_id(href)
        if not book_id or book_id in seen:
            continue
        title = link.get_text(strip=True)
        if not title or len(title) < 2:
            continue
        low = title.lower()
        if low in {"все книги", "купить", "читать", "скачать", "написать рецензию", "обсудить книгу"}:
            continue
        rank += 1
        seen.add(book_id)
        records.append(
            BookRecord(
                source="bookmix",
                external_id=book_id,
                title=title,
                authors=[],
                rank=rank,
                url=book_url(book_id),
                normalized_title=normalize_title(title),
                normalized_authors=[],
            )
        )
    return records


def parse_book_page(html: str, book_id: str | None = None) -> BookRecord | None:
    soup = BeautifulSoup(html, "lxml")
    ld = _json_ld(html)

    title = None
    if ld and ld.get("name"):
        title = str(ld["name"]).strip()
    if not title:
        h1 = soup.select_one("h1")
        title = h1.get_text(strip=True) if h1 else ""
    if not title:
        return None

    authors: list[str] = []
    if ld:
        author = ld.get("author")
        if isinstance(author, dict) and author.get("name"):
            authors.append(str(author["name"]).strip())
        elif isinstance(author, list):
            for item in author:
                if isinstance(item, dict) and item.get("name"):
                    authors.append(str(item["name"]).strip())
    if not authors:
        for link in soup.select('a[href*="bookauthor.phtml"]'):
            name = link.get_text(strip=True)
            if name and name not in authors:
                authors.append(name)
                break

    rating: float | None = None
    votes: int | None = None
    if ld:
        agg = ld.get("aggregateRating") or {}
        if isinstance(agg, dict):
            if agg.get("ratingValue") is not None:
                try:
                    rating = float(str(agg["ratingValue"]).replace(",", "."))
                except ValueError:
                    pass
            if agg.get("ratingCount") is not None:
                try:
                    votes = int(agg["ratingCount"])
                except ValueError:
                    pass

    if rating is None:
        node = soup.select_one("h6.fw400 span")
        if node:
            try:
                rating = float(node.get_text(strip=True).replace(",", "."))
            except ValueError:
                pass

    if votes is None:
        readers = READERS_RE.search(soup.get_text(" ", strip=True))
        if readers:
            votes = int(readers.group(1))

    genres: list[str] = []
    for link in soup.select('a[itemprop="genre"], span[itemprop="keywords"]'):
        text = link.get_text(strip=True)
        if text and len(text) < 50 and text not in genres:
            genres.append(text)
    genres = genres[:15]

    bid = book_id
    if not bid and ld and ld.get("url"):
        bid = _extract_id(str(ld["url"]))
    if not bid:
        canonical = soup.select_one('link[rel="canonical"]')
        if canonical and canonical.get("href"):
            bid = _extract_id(canonical["href"])
    if not bid:
        return None

    return BookRecord(
        source="bookmix",
        external_id=str(bid),
        title=title,
        authors=authors[:5],
        rating=rating,
        rating_max=5.0,
        vote_count=votes,
        genres=genres,
        url=book_url(bid),
        normalized_title=normalize_title(title),
        normalized_authors=normalize_authors(authors),
    )
