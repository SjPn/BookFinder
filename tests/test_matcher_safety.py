from bookfinder.matcher import MATCH_THRESHOLD, score_pair
from bookfinder.models import BookRecord
from bookfinder.normalize import normalize_authors, normalize_title


def _rec(title: str, authors: list[str], external_id: str = "1") -> BookRecord:
    return BookRecord(
        source="test",
        external_id=external_id,
        title=title,
        authors=authors,
        normalized_title=normalize_title(title),
        normalized_authors=normalize_authors(authors),
    )


def test_verne_not_matched_to_spider_island() -> None:
    left = _rec("Таинственный остров", ["Жюль Верн"])
    right = _rec("Остров", ["Ширли Рейн"], "17447")
    assert score_pair(left, right) < MATCH_THRESHOLD


def test_same_book_matches() -> None:
    left = _rec("Таинственный остров", ["Жюль Верн"])
    right = _rec("Таинственный остров", ["Жюль Верн"], "2")
    assert score_pair(left, right) >= MATCH_THRESHOLD


def test_numeric_title_preserved() -> None:
    left = _rec("78", ["Макс Фрай"])
    right = _rec("78", ["Макс Фрай"], "22066")
    assert score_pair(left, right) >= MATCH_THRESHOLD


def test_short_surname_partial_not_enough() -> None:
    left = _rec("Жажда жизни", ["Ирвинг Стоун"])
    right = _rec("Жажда", ["Кристофер Пайк"], "3")
    assert score_pair(left, right) == 0.0
