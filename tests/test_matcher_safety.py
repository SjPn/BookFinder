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


def test_name_order_does_not_matter() -> None:
    left = _rec("Профессия: ведьма", ["Громыко Ольга"])
    right = _rec("Профессия: ведьма", ["Ольга Громыко"], "2")
    assert score_pair(left, right) >= MATCH_THRESHOLD


def test_shared_first_name_not_enough() -> None:
    left = _rec("Ведьма", ["Ольга Громыко"])
    right = _rec("Хранитель", ["Ольга Голотвина"], "3")
    assert score_pair(left, right) == 0.0


def test_near_typo_author_still_ok() -> None:
    # Same surname after normalize; title identical.
    left = _rec("Дюна", ["Фрэнк Герберт"])
    right = _rec("Дюна", ["Френк Герберт"], "2")
    # Given names differ slightly, but surname matches exactly → ok.
    assert score_pair(left, right) >= MATCH_THRESHOLD


def test_similar_but_different_title_rejected() -> None:
    left = _rec("Таинственный остров", ["Жюль Верн"])
    right = _rec("Остров", ["Жюль Верн"], "3")
    assert score_pair(left, right) == 0.0


def test_short_asian_name_tokens_match() -> None:
    left = _rec("Возрожденное орудие", ["Юн Ха Ли"])
    right = _rec("Возрожденное орудие", ["Юн Ха Ли"], "2")
    assert score_pair(left, right) >= MATCH_THRESHOLD


def test_threshold_is_near_exact() -> None:
    assert MATCH_THRESHOLD >= 0.98

