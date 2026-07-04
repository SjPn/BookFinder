"""Filter catalog genres: drop rare tags and proper-noun noise."""

from __future__ import annotations

import re

MIN_GENRE_COUNT = 3

GENRE_WORDS = {
    "фантастика",
    "фэнтези",
    "детектив",
    "детективы",
    "приключения",
    "роман",
    "повесть",
    "рассказ",
    "ужасы",
    "мистика",
    "юмор",
    "сатира",
    "боевик",
    "триллер",
    "эротика",
    "драма",
    "сказка",
    "поэзия",
    "биография",
    "мемуары",
    "история",
    "легенды",
    "предания",
    "мифы",
    "мифология",
    "эпос",
    "философия",
    "политика",
    "публицистика",
    "религиозное",
    "религия",
    "фанфик",
    "фанфики",
    "экранизации",
    "кинороманы",
    "современность",
    "ироническое",
    "мистическая",
    "городское",
    "космоопера",
    "антиутопия",
    "утопия",
    "космос",
    "магия",
    "эльфы",
    "вампиры",
    "оборотни",
    "зомби",
    "абсурд",
    "абсурдизм",
    "авторский",
    "сборник",
    "антология",
    "переводы",
    "мелодрама",
    "мелодрамы",
    "новелла",
    "новеллы",
    "проза",
    "поэзия",
    "litrpg",
    "realrpg",
    "adult",
    "fiction",
    "fantasy",
    "horror",
    "sci-fi",
    "sf",
}

ALLOWED_PHRASES = {
    "young adult",
    "young-adult",
    "young-adult fiction",
    "new adult",
    "dark fantasy",
    "science fiction",
    "space opera",
    "мистика. готика. ужасы",
    "русская фантастика",
    "русское фэнтези",
    "русская фэнтези",
    "русской/славянской",
    "легенды и предания",
    "мифы. легенды. эпос",
    "биографии и мемуары",
    "книга-игра",
    "книги-игры",
    "литrpg / литрпg",
    "litrpg / литрпг",
    "realrpg / реалрпг",
    "азиатское фэнтези",
    "азиатское фэнтези / ориентальное фэнтези",
}

# Full genre labels that are really places / countries / imprints / franchises.
BLOCKED_EXACT = {
    "япония",
    "китай",
    "корея",
    "индия",
    "ирландия",
    "скандинавия",
    "скандинавской",
    "америка",
    "европа",
    "азия",
    "москва",
    "лондон",
    "марс",
    "дания",
    "атлантида",
    "донбасс",
    "крым",
    "санкт-петербург",
    "star trek",
    "star wars",
    "warhammer",
    "warcraft",
    "warhammer 40000",
    "гарри поттер",
    "ведьмак",
    "шерлок холмс",
    "minecraft",
    "minecraft / майнкрафт",
    "fortnite",
    "dishonored",
    "avengers",
    "disney",
    "netflix",
    "mortal kombat",
    "s.t.a.l.k.e.r.",
    "stalker",
    "k-pop",
    "fanzon",
    "red violet",
    "букток",
    "booktok",
    "миры стругацких",
    "миры будущего",
    "миры ника перумова",
    "«зона посещения»",
    "зона посещения",
    "лабиринты ехо",
    "сага о конане",
    "редакция елены шубиной",
    "вторая мировая война",
    "древний китай",
    "древний египет",
    "древняя греция",
    "южная корея",
    "северная америка",
    "дальний восток",
    "ближний восток",
    "дикий запад",
    "красная армия",
    "средневековая европа",
    "средневековая англия",
    "викторианская англия",
    "дореволюционная россия",
    "россия xix века",
    "россия начала xx века",
    "царская россия",
    "китай, япония",
    "the new york times",
    "new york times",
    "бестселлеры the new york times",
    "бестселлеры amazon",
    "miф проза",
    "миф проза",
    "серия «академия магии»",
    "петр первый",
    "николай второй",
    "александр первый",
    "наполеон бонапарт",
    "эраст фандорin",
}

AGE_RATING_RE = re.compile(r"^\d+\+$")
YEAR_RE = re.compile(r"^(?:\d{1,4}|x{1,2}\s*век)$", re.I)
TECH_PREFIX_RE = re.compile(r"^(?:tn_|child_|sf_|det_|inoag|ugryumova|darknet|golem|necro)", re.I)
PERSON_PAIR_RE = re.compile(r"[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}")
LATIN_NAME_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")
LATIN_TOKEN_RE = re.compile(r"\b[A-Za-z][A-Za-z.+-]{2,}\b")
ALLOWED_LATIN = {
    "sf",
    "litrpg",
    "realrpg",
    "rpg",
    "adult",
    "young",
    "new",
    "fiction",
    "fantasy",
    "horror",
    "dark",
    "science",
    "space",
    "opera",
    "hard",
    "soft",
    "love",
    "modern",
    "middle",
    "grade",
    "non",
    "true",
    "crime",
    "book",
    "game",
    "fan",
    "fic",
    "fanfic",
    "lit",
    "ya",
    "mg",
    "na",
    "ff",
    "sci",
    "fi",
    "real",
    "rpg",
}


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).casefold()


def _blocked_exact(text: str) -> bool:
    folded = _fold(text)
    if folded in BLOCKED_EXACT:
        return True
    if folded in ALLOWED_PHRASES:
        return False
    for blocked in BLOCKED_EXACT:
        if len(blocked) >= 8 and blocked in folded:
            return True
    return False


def _looks_like_person_name(text: str) -> bool:
    folded = _fold(text)
    if any(marker in folded for marker in ("редакция ", " миры ", "имени ", "серия «", "бестселлеры ")):
        return True
    if folded in ALLOWED_PHRASES:
        return False
    for pair in PERSON_PAIR_RE.findall(text):
        pf = pair.casefold()
        if pf in ALLOWED_PHRASES:
            continue
        if all(part in GENRE_WORDS for part in pf.split()):
            continue
        return True
    if LATIN_NAME_RE.search(text):
        return True
    return False


def _latin_proper_noun(text: str) -> bool:
    folded = _fold(text)
    if folded in ALLOWED_PHRASES:
        return False
    for token in LATIN_TOKEN_RE.findall(text):
        low = token.casefold().strip(".")
        if low in ALLOWED_LATIN:
            continue
        if token.isupper() and len(token) <= 4:
            continue
        if re.match(r"^[A-Z]", token) and low not in ALLOWED_LATIN:
            return True
    return False


def _title_case_proper(text: str) -> bool:
    folded = _fold(text)
    if folded in ALLOWED_PHRASES:
        return False
    words = [w for w in re.split(r"[\s/|]+", text.strip()) if w and not w.isdigit()]
    if len(words) < 2:
        return False
    caps = sum(1 for w in words if re.match(r"^[А-ЯЁA-Z]", w))
    if caps >= 2 and caps >= len(words) * 0.55:
        if any(w.casefold() in GENRE_WORDS for w in words):
            return False
        return True
    return False


def is_catalog_genre(name: str, count: int) -> bool:
    text = (name or "").strip()
    if not text or count < MIN_GENRE_COUNT:
        return False

    folded = _fold(text)
    if folded in ALLOWED_PHRASES:
        return True
    if AGE_RATING_RE.match(text) or YEAR_RE.match(text):
        return False
    if TECH_PREFIX_RE.search(text):
        return False
    if _blocked_exact(text):
        return False
    if _looks_like_person_name(text):
        return False
    if _latin_proper_noun(text):
        return False
    if _title_case_proper(text):
        return False

    words = [w for w in re.split(r"[\s/,.-]+", folded) if w]
    if len(words) == 1:
        word = words[0]
        if word in GENRE_WORDS:
            return True
        if re.match(r"^[А-ЯЁA-Z]", text) and word not in GENRE_WORDS:
            return False
    return True


def filter_work_genres(genres: list[str], counts: dict[str, int] | None = None) -> list[str]:
    out: list[str] = []
    for genre in genres:
        if not genre:
            continue
        count = counts.get(genre, MIN_GENRE_COUNT) if counts else MIN_GENRE_COUNT
        if is_catalog_genre(genre, count):
            out.append(genre)
    return out
