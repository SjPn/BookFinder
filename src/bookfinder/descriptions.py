"""Extract short book descriptions from cached source HTML."""

from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

MAX_LEN = 900


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _trim(text: str, limit: int = MAX_LEN) -> str:
    text = _normalize(text)
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + "…"


def _strip_leading_title_author(text: str, title: str | None = None) -> str:
    if title:
        t = title.strip()
        if text.lower().startswith(t.lower()):
            text = text[len(t) :].lstrip(" -–—.:,")
    if " - " in text[:100]:
        head, tail = text.split(" - ", 1)
        if len(head) < 80 and len(tail) > 40:
            text = tail
    parts = text.split(". ", 1)
    if len(parts) == 2 and len(parts[0]) < 50 and len(parts[1]) > 40:
        text = parts[1]
    return text.strip()


def extract_fw_description(html: str, title: str | None = None) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    meta = soup.select_one('meta[name="description"]')
    if meta and meta.get("content"):
        text = _strip_leading_title_author(meta["content"].strip(), title)
        if len(text) >= 40:
            return _trim(text)

    for p in soup.select("p"):
        text = _normalize(p.get_text(" ", strip=True))
        if len(text) < 80 or "fb2.zip" in text.lower() or text.startswith("Автор:"):
            continue
        if text.startswith("Жанр:") or text.startswith("Год:"):
            continue
        return _trim(_strip_leading_title_author(text, title))
    return None


def extract_bookmix_description(html: str) -> str | None:
    for block in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.I | re.S,
    ):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            desc = item.get("description")
            if isinstance(desc, str) and len(desc.strip()) >= 40:
                return _trim(desc.strip())
    soup = BeautifulSoup(html, "lxml")
    node = soup.select_one(".book-description, .annotation, [itemprop=description]")
    if node:
        text = _normalize(node.get_text(" ", strip=True))
        if len(text) >= 40:
            return _trim(text)
    return None


def extract_fantlab_description(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    for selector in (
        "div.about__text",
        "div.work-description",
        "div.annotation",
        "div[itemprop=description]",
    ):
        node = soup.select_one(selector)
        if not node:
            continue
        text = _normalize(node.get_text(" ", strip=True))
        if len(text) >= 40:
            return _trim(text)
    return None
