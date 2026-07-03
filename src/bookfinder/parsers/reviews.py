"""Parse book reviews from Fantasy-Worlds, FantLab, LiveLib."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from bookfinder.parsers.fantasy_worlds import book_url as fw_book_url

MIN_REVIEW_LEN = 25


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _valid_review(text: str) -> bool:
    return len(text) >= MIN_REVIEW_LEN


def parse_fantasy_worlds_comments(html: str, book_id: str | None = None) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    reviews: list[dict[str, Any]] = []
    seen: set[str] = set()

    for block in soup.select("div.comm_body"):
        user_el = block.select_one("span.comm_user")
        date_el = block.select_one("span.comm_date")
        msg_el = block.select_one("div.comm_mesage")
        if not msg_el:
            continue
        for img in msg_el.select("img"):
            img.decompose()
        text = _clean_text(msg_el.get_text(" ", strip=True))
        if not _valid_review(text):
            continue
        key = text[:120]
        if key in seen:
            continue
        seen.add(key)

        mod = block.select_one('[id^="comment_moderate_block_"]')
        ext_id = None
        if mod and mod.get("id"):
            ext_id = mod["id"].replace("comment_moderate_block_", "")

        reviews.append(
            {
                "source": "fantasy_worlds",
                "external_id": ext_id,
                "author": user_el.get_text(strip=True) if user_el else None,
                "date": _clean_text(date_el.get_text(" ", strip=True)) if date_el else None,
                "text": text,
                "url": fw_book_url(book_id) if book_id else None,
            }
        )
    return reviews


def parse_fantlab_work_page(html: str, work_id: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    reviews: list[dict[str, Any]] = []
    seen: set[str] = set()
    base = f"https://fantlab.ru/work{work_id}"

    selectors = (
        "div.blogpost",
        "div.workreview",
        "div.response",
        "div.review_item",
        "article.review",
    )
    for selector in selectors:
        for block in soup.select(selector):
            review = _fantlab_block_to_review(block, work_id, base, seen)
            if review:
                reviews.append(review)

    # Fallback: отзывы в таблицах / блоках с текстом рецензии
    for link in soup.select('a[href*="/workreview"]'):
        parent = link.find_parent("div", class_=True)
        if not parent:
            continue
        review = _fantlab_block_to_review(parent, work_id, base, seen)
        if review:
            reviews.append(review)

    return reviews


def _fantlab_block_to_review(
    block: Tag,
    work_id: str,
    base: str,
    seen: set[str],
) -> dict[str, Any] | None:
    text_el = block.select_one(
        ".blogpost_text, .workreview_text, .response_text, .review_text, .text"
    )
    if not text_el:
        text_el = block
    text = _clean_text(text_el.get_text(" ", strip=True))
    if not _valid_review(text):
        return None
    key = text[:120]
    if key in seen:
        return None
    seen.add(key)

    author_el = block.select_one("a[href*='/user'], .author, .username")
    date_el = block.select_one("time, .date, .datetime")
    href = block.select_one('a[href*="/workreview"]')
    url = urljoin(base, href["href"]) if href and href.get("href") else base

    return {
        "source": "fantlab",
        "external_id": None,
        "author": author_el.get_text(strip=True) if author_el else None,
        "date": date_el.get_text(strip=True) if date_el else None,
        "text": text,
        "url": url,
    }


def parse_fantlab_api_responses(data: dict | list) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    seen: set[str] = set()
    items = data if isinstance(data, list) else data.get("responses") or data.get("items") or []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = _clean_text(str(item.get("text") or item.get("message") or item.get("body") or ""))
        if not _valid_review(text):
            continue
        key = text[:120]
        if key in seen:
            continue
        seen.add(key)
        reviews.append(
            {
                "source": "fantlab",
                "external_id": str(item.get("id") or ""),
                "author": item.get("user_name") or item.get("author"),
                "date": item.get("date") or item.get("created"),
                "text": text,
                "url": item.get("url"),
            }
        )
    return reviews


def parse_livelib_reviews(html: str, book_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    reviews: list[dict[str, Any]] = []
    seen: set[str] = set()

    blocks = soup.select(
        ".review-card, .bc-review, .review-item, article.review, "
        "[itemprop=review], .reader-review, .review-text-block"
    )
    if not blocks:
        blocks = soup.select(".review, .comment-item")

    for block in blocks:
        text_el = block.select_one(
            "[itemprop=reviewBody], .review-text, .review-body, .text, .comment-text"
        )
        if not text_el:
            text_el = block
        text = _clean_text(text_el.get_text(" ", strip=True))
        if not _valid_review(text):
            continue
        key = text[:120]
        if key in seen:
            continue
        seen.add(key)

        author_el = block.select_one("[itemprop=author], .author, .user-name, a[href*='/reader/']")
        date_el = block.select_one("time, .date, [itemprop=datePublished]")
        rating_el = block.select_one("[itemprop=ratingValue], .rating")

        rating = None
        if rating_el:
            try:
                rating = float(rating_el.get_text(strip=True).replace(",", "."))
            except ValueError:
                rating = None

        reviews.append(
            {
                "source": "livelib",
                "external_id": block.get("id"),
                "author": author_el.get_text(strip=True) if author_el else None,
                "date": date_el.get_text(strip=True) if date_el else None,
                "rating": rating,
                "text": text,
                "url": book_url,
            }
        )
    return reviews


def livelib_reviews_url(book_url: str) -> str:
    base = book_url.rstrip("/")
    if base.endswith("/reviews"):
        return base
    if base.endswith("/otzivi"):
        return base
    return f"{base}/reviews"


def dedupe_reviews(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for review in reviews:
        key = _clean_text(review.get("text", ""))[:160].lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(review)
    return out
