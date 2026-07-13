from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from bookfinder.models import BookRecord
from bookfinder.normalize import normalize_authors, normalize_title

BASE_URL = "https://loveread.ec/"

BOOK_ID_RE = re.compile(r"book-comments\.php\?book=(\d+)", re.I)
VIEWS_RE = re.compile(r"просмотров:\s*([\d\s]+)", re.I)
RATING_RE = re.compile(r"Рейтинг онлайн книги:\s*([\d.,]+)", re.I)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def book_url(book_id: str | int) -> str:
    return urljoin(BASE_URL, f"book-comments.php?book={book_id}")


def genre_url(genre_id: str | int) -> str:
    return urljoin(BASE_URL, f"genre.php?genre={genre_id}")


def page_url(page: str | int) -> str:
    return urljoin(BASE_URL, f"page.php?page={page}")


def _parse_int(text: str) -> int | None:
    digits = re.sub(r"\s+", "", text.strip())
    if not digits.isdigit():
        return None
    return int(digits)


def _field_value(block: BeautifulSoup, label: str) -> str | None:
    for span in block.select("span"):
        if span.get_text(strip=True).startswith(label):
            parts: list[str] = []
            for sibling in span.next_siblings:
                if getattr(sibling, "name", None) == "br":
                    break
                if getattr(sibling, "name", None) == "span":
                    break
                if isinstance(sibling, str):
                    parts.append(sibling.strip())
                elif getattr(sibling, "name", None) == "a":
                    parts.append(sibling.get_text(" ", strip=True))
                elif getattr(sibling, "name", None) == "strong":
                    parts.append(sibling.get_text(" ", strip=True))
            value = " ".join(part for part in parts if part).strip()
            return value or None
    return None


def parse_list_page(html: str, list_name: str = "") -> list[BookRecord]:
    soup = BeautifulSoup(html, "lxml")
    records: list[BookRecord] = []
    seen: set[str] = set()

    for block in soup.select("div.blockBook"):
        link = block.select_one('a[href*="book-comments.php?book="]')
        if not link:
            continue
        match = BOOK_ID_RE.search(link.get("href", ""))
        if not match:
            continue
        book_id = match.group(1)
        if book_id in seen:
            continue

        title_el = block.select_one(".blNameBook h3, h3")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            continue

        authors: list[str] = []
        for author_link in block.select('a[href*="biography-author.php"] strong, a[href*="biography-author.php"]'):
            name = author_link.get_text(strip=True)
            if name and name not in authors:
                authors.append(name)

        genres = []
        for genre_link in block.select('.blGenres a[href*="genre.php"]'):
            genre = genre_link.get_text(strip=True).strip("«»")
            if genre:
                genres.append(genre)

        footer_text = block.select_one(".blFooter, .blCount")
        footer = footer_text.get_text("\n", strip=True) if footer_text else block.get_text("\n", strip=True)

        views = None
        views_match = VIEWS_RE.search(footer)
        if views_match:
            views = _parse_int(views_match.group(1))

        rating = None
        rating_match = RATING_RE.search(footer)
        if rating_match:
            try:
                rating = float(rating_match.group(1).replace(",", "."))
            except ValueError:
                rating = None

        year = None
        year_raw = _field_value(block, "Год:")
        if year_raw:
            year_match = YEAR_RE.search(year_raw)
            if year_match:
                year = int(year_match.group(0))

        seen.add(book_id)
        records.append(
            BookRecord(
                source="loveread",
                external_id=book_id,
                title=title,
                authors=authors,
                rating=rating if rating and rating > 0 else None,
                rating_max=5.0,
                # Do not store page views as vote_count — they inflated aggregates to 10/10.
                vote_count=None,
                year=year,
                url=book_url(book_id),
                genres=genres,
                normalized_title=normalize_title(title),
                normalized_authors=normalize_authors(authors),
            )
        )

    return records


def discover_genre_ids(html: str) -> list[str]:
    return sorted(set(re.findall(r"genre\.php\?genre=(\d+)", html)), key=int)


def discover_max_page(html: str) -> int:
    pages = [int(value) for value in re.findall(r"page\.php\?page=(\d+)", html)]
    return max(pages) if pages else 0
