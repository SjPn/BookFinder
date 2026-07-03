from __future__ import annotations

import re
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from bookfinder.models import BookRecord
from bookfinder.normalize import normalize_authors, normalize_title

BASE_URL = "https://www.livelib.ru"

SUBPAGE_MARKERS = ("/readers", "/reviews", "/quotes", "/editions")


def _is_book_href(href: str) -> bool:
    if not href.startswith("/book/"):
        return False
    return not any(marker in href for marker in SUBPAGE_MARKERS)


def _parse_ll_redirect_blocks(html: str) -> list[BookRecord]:
    soup = BeautifulSoup(html, "lxml")
    records: list[BookRecord] = []
    seen: set[str] = set()

    for block in soup.select("div.ll-redirect"):
        data_link = block.get("data-link", "")
        title_el = block.select_one("a.title")
        author_el = block.select_one("a.description[href*='/author/']")
        rating_el = block.select_one(".rating-value[itemprop='ratingValue'], .rating-value")

        href = data_link or (title_el.get("href", "") if title_el else "")
        if not _is_book_href(href):
            continue

        book_id = href.rstrip("/").split("/")[-1]
        if book_id in seen:
            continue

        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            continue

        authors: list[str] = []
        if author_el:
            authors = [author_el.get_text(strip=True)]

        rating = None
        if rating_el:
            try:
                rating = float(rating_el.get_text(strip=True).replace(",", "."))
            except ValueError:
                rating = None

        seen.add(book_id)
        records.append(
            BookRecord(
                source="livelib",
                external_id=book_id,
                title=title,
                authors=authors,
                rating=rating,
                rating_max=5.0,
                rank=len(records) + 1,
                url=urljoin(BASE_URL, href),
                normalized_title=normalize_title(title),
                normalized_authors=normalize_authors(authors),
            )
        )

    return records


def _parse_bc_items(html: str) -> list[BookRecord]:
    soup = BeautifulSoup(html, "lxml")
    records: list[BookRecord] = []

    for idx, item in enumerate(soup.select(".bc-item, .book-item, article.bookcard"), start=1):
        link = item.select_one('a[href*="/book/"]')
        title_el = item.select_one(".bc-title, .book-title, h3 a, .title a")
        author_el = item.select_one(".bc-author, .book-author, .author a, .authors")
        rating_el = item.select_one(".rating-value, .rating, [itemprop='ratingValue']")

        if not link or not title_el:
            continue

        href = link.get("href", "")
        if not _is_book_href(href):
            continue

        book_id = href.rstrip("/").split("/")[-1]
        title = title_el.get_text(strip=True)
        authors = (
            [a.strip() for a in re.split(r",|/", author_el.get_text(strip=True)) if a.strip()]
            if author_el
            else []
        )

        rating = None
        if rating_el:
            try:
                rating = float(rating_el.get_text(strip=True).replace(",", "."))
            except ValueError:
                rating = None

        records.append(
            BookRecord(
                source="livelib",
                external_id=book_id,
                title=title,
                authors=authors,
                rating=rating,
                rating_max=5.0,
                rank=idx,
                url=urljoin(BASE_URL, href),
                normalized_title=normalize_title(title),
                normalized_authors=normalize_authors(authors),
            )
        )

    return records


def _parse_book_items(html: str) -> list[BookRecord]:
    soup = BeautifulSoup(html, "lxml")
    records: list[BookRecord] = []

    for idx, item in enumerate(soup.select("li.book-item__item, .book-item__item"), start=1):
        title_el = item.select_one("a.book-item__title")
        author_el = item.select_one("a.book-item__author")
        rating_el = item.select_one(".book-item__rating")

        if not title_el:
            continue

        href = title_el.get("href", "")
        if not _is_book_href(href):
            continue

        book_id = href.rstrip("/").split("/")[-1]
        title = title_el.get_text(strip=True)
        authors = [author_el.get_text(strip=True)] if author_el else []

        rating = None
        if rating_el:
            try:
                rating = float(rating_el.get_text(strip=True).replace(",", "."))
            except ValueError:
                rating = None

        records.append(
            BookRecord(
                source="livelib",
                external_id=book_id,
                title=title,
                authors=authors,
                rating=rating,
                rating_max=5.0,
                rank=idx,
                url=urljoin(BASE_URL, href),
                normalized_title=normalize_title(title),
                normalized_authors=normalize_authors(authors),
            )
        )

    return records


def parse_top_page(html: str) -> list[BookRecord]:
    for parser in (_parse_book_items, _parse_ll_redirect_blocks, _parse_bc_items):
        records = parser(html)
        if records:
            return records[:100]
    return []


def parse_search_page(html: str, query_title: str, query_authors: list[str]) -> list[BookRecord]:
    records = _parse_ll_redirect_blocks(html)
    if not records:
        records = _parse_bc_items(html)
    for record in records:
        record.normalized_title = normalize_title(record.title)
        record.normalized_authors = normalize_authors(record.authors)
    return records


def parse_book_page(html: str, book_id: str) -> BookRecord | None:
    soup = BeautifulSoup(html, "lxml")
    title_el = soup.select_one("h1, .book-title, #book-title")
    if not title_el:
        return None

    title = title_el.get_text(strip=True)
    authors: list[str] = []
    for author_link in soup.select('a[href*="/author/"]')[:5]:
        name = author_link.get_text(strip=True)
        if name and name not in authors:
            authors.append(name)

    rating = None
    rating_el = soup.select_one(".rating-value, .rating-number, [itemprop='ratingValue']")
    if rating_el:
        try:
            rating = float(rating_el.get_text(strip=True).replace(",", "."))
            if rating > 5:
                rating = min(rating, 10.0)
        except ValueError:
            rating = None

    genres: list[str] = []
    for link in soup.select('a[href*="/genre/"], a[href*="/genres/"]'):
        text = link.get_text(strip=True)
        if text and text not in genres:
            genres.append(text)

    return BookRecord(
        source="livelib",
        external_id=book_id,
        title=title,
        authors=authors,
        rating=rating,
        rating_max=5.0,
        url=f"{BASE_URL}/book/{book_id}",
        genres=genres,
        normalized_title=normalize_title(title),
        normalized_authors=normalize_authors(authors),
    )


def search_query(book: BookRecord) -> str:
    if book.authors:
        return f"{book.authors[0]} {book.title}"
    return book.title


def search_url(title: str, author: str | None = None) -> str:
    query = f"{author} {title}".strip() if author else title
    return f"{BASE_URL}/find/{quote(query)}"
