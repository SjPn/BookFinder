from __future__ import annotations

import re
import unicodedata

STRIP_WORDS = {
    "сборник",
    "книга",
    "том",
    "часть",
    "комплект",
    "издание",
    "роман",
    "повесть",
    "рассказ",
    "иллюстрации",
    "полное",
    "собрание",
    "сочинений",
    "иллюстр",
}

SERIES_PREFIX_RE = re.compile(
    r"^(?:колесо времени|властелин колец|звездные войны|гарри поттер|"
    r"песнь льда и пламени|марс|основание|дюна|дискордия|"
    r"expanse|the)\s+",
    re.I,
)


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = text.replace("ё", "е")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_title(title: str) -> str:
    original = _fold(title)
    text = original
    if ":" in text:
        tail = text.split(":")[-1].strip()
        if len(tail) >= 4:
            text = tail
    text = SERIES_PREFIX_RE.sub("", text)
    text = re.sub(r"\b\d+\b", " ", text)
    text = re.sub(r"\bтом\s+\d+\b", " ", text)
    text = re.sub(r"\bкнига\s+\d+\b", " ", text)
    for word in STRIP_WORDS:
        text = re.sub(rf"\b{word}\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # Keep pure numeric titles (e.g. "78") — stripping digits would empty them.
    if not text and original:
        return original
    return text


def author_surname(author: str) -> str:
    parts = [p for p in normalize_author(author).split() if len(p) > 2]
    return parts[-1] if parts else normalize_author(author)


def _normalize_person_name(text: str) -> str:
    text = _fold(text)
    text = re.sub(r"\b[а-яa-z]\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_author(author: str) -> str:
    return _normalize_person_name(author)


def normalize_authors(authors: list[str]) -> list[str]:
    return sorted({normalize_author(a) for a in authors if a.strip()})


def make_match_key(title: str, authors: list[str]) -> str:
    norm_title = normalize_title(title)
    norm_authors = normalize_authors(authors)
    if norm_authors:
        return f"{author_surname(norm_authors[0])}|{norm_title}"
    return f"|{norm_title}"
