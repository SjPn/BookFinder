from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from bookfinder.models import BookRecord
from bookfinder.normalize import normalize_authors, normalize_title

BASE_URL = "https://readrate.com"


def parse_rating_page(html: str, list_name: str = "") -> list[BookRecord]:
    soup = BeautifulSoup(html, "lxml")
    records: list[BookRecord] = []
    seen: set[str] = set()

    for link in soup.select('a[href*="/rus/books/"]'):
        href = link.get("href", "")
        if not href or href.endswith(("most-commented", "most-rated")):
            continue
        slug = href.rstrip("/").split("/")[-1]
        if slug in seen or slug in {"most-commented", "most-rated"}:
            continue

        title = link.get_text(strip=True)
        if not title or len(title) < 2:
            continue

        seen.add(slug)
        records.append(
            BookRecord(
                source="readrate",
                external_id=slug,
                title=title,
                authors=[],
                rank=len(records) + 1,
                url=urljoin(BASE_URL, href),
                normalized_title=normalize_title(title),
                normalized_authors=[],
            )
        )

    return records
