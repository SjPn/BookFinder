from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from bookfinder.models import BookRecord
from bookfinder.normalize import normalize_authors, normalize_title

BASE_URL = "http://www.kubikus.ru/"

TXID_RE = re.compile(r"txid=(\d+)", re.I)
RATING_RE = re.compile(r"([\d,]+)")
VOTES_RE = re.compile(r"(\d+)\s*голос", re.I)


def book_url(txid: str | int) -> str:
    return urljoin(BASE_URL, f"textinfo.asp?txid={txid}")


def _parse_rating_text(text: str) -> float | None:
    match = RATING_RE.search(text.replace(" ", ""))
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def _parse_votes(text: str) -> int | None:
    match = VOTES_RE.search(text)
    if match:
        return int(match.group(1))
    return None


def _parse_genres(block: BeautifulSoup) -> list[str]:
    genres: list[str] = []
    for item in block.select("li.author-selection__list"):
        label = item.select_one("span")
        if not label or "Жанр" not in label.get_text():
            continue
        raw = item.get_text(" ", strip=True)
        raw = raw.split(":", 1)[-1].strip()
        genres = [part.strip() for part in raw.split(",") if part.strip()]
        break
    return genres[:12]


def _parse_authors(block: BeautifulSoup) -> list[str]:
    for item in block.select("li.author-selection__list"):
        label = item.select_one("span")
        if not label or "Автор" not in label.get_text():
            continue
        names: list[str] = []
        for link in item.select("a.profile b, a.profile"):
            name = link.get_text(" ", strip=True)
            if name:
                names.append(name)
        if names:
            return names
        raw = item.get_text(" ", strip=True).split(":", 1)[-1].strip()
        if raw:
            return [part.strip() for part in re.split(r",\s*", raw) if part.strip()]
    return []


def _block_to_record(block: BeautifulSoup, rank: int | None = None) -> BookRecord | None:
    link = block.select_one('a[href*="textinfo.asp?txid="]')
    if not link:
        return None
    href = link.get("href", "")
    tx_match = TXID_RE.search(href)
    if not tx_match:
        return None
    txid = tx_match.group(1)

    title_el = block.select_one("a.title-other, h1.inner-title, .title-other")
    title = title_el.get_text(strip=True) if title_el else ""
    if not title:
        return None

    rating_el = block.select_one(".rating-result__text span")
    rating = _parse_rating_text(rating_el.get_text()) if rating_el else None
    votes_el = block.select_one("p.comment-link")
    votes = _parse_votes(votes_el.get_text()) if votes_el else None

    authors = _parse_authors(block)
    genres = _parse_genres(block)

    return BookRecord(
        source="kubikus",
        external_id=txid,
        title=title,
        authors=authors,
        rating=rating,
        rating_max=5.0,
        vote_count=votes,
        rank=rank,
        genres=genres,
        url=book_url(txid),
        normalized_title=normalize_title(title),
        normalized_authors=normalize_authors(authors),
    )


def parse_list_page(html: str) -> list[BookRecord]:
    soup = BeautifulSoup(html, "lxml")
    records: list[BookRecord] = []
    seen: set[str] = set()
    rank = 0
    for wrap in soup.select("div.work-wrap"):
        block = wrap.select_one("div.author-selection")
        if not block:
            continue
        record = _block_to_record(block)
        if not record or record.external_id in seen:
            continue
        rank += 1
        record.rank = rank
        seen.add(record.external_id)
        records.append(record)
    return records


def parse_book_page(html: str, txid: str | None = None) -> BookRecord | None:
    soup = BeautifulSoup(html, "lxml")
    block = soup.select_one("div.author-selection")
    if not block:
        return None
    record = _block_to_record(block)
    if not record:
        return None
    if txid:
        record.external_id = str(txid)
        record.url = book_url(txid)

    h1 = soup.select_one("h1.inner-title")
    if h1:
        title = h1.get_text(strip=True)
        if title:
            record.title = title
            record.normalized_title = normalize_title(title)

    agg = soup.select_one('[itemprop="aggregateRating"] meta[itemprop="ratingValue"]')
    if record.rating is None and agg and agg.get("content"):
        try:
            record.rating = float(agg["content"].replace(",", "."))
        except ValueError:
            pass
    review_count = soup.select_one('meta[itemprop="reviewCount"]')
    if review_count and review_count.get("content") and record.vote_count is None:
        try:
            record.vote_count = int(review_count["content"])
        except ValueError:
            pass

    if not record.genres:
        record.genres = _parse_genres(block)
    return record
