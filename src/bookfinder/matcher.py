from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz

from bookfinder.models import BookRecord
from bookfinder.normalize import author_surname, make_match_key, normalize_authors, normalize_title

MATCH_THRESHOLD = 0.78


@dataclass(slots=True)
class MatchResult:
    fantlab: BookRecord
    livelib: BookRecord | None
    method: str
    score: float
    matched: bool


@dataclass(slots=True)
class MatchReport:
    total_fantlab: int
    total_livelib: int
    matched: list[MatchResult] = field(default_factory=list)
    unmatched_fantlab: list[BookRecord] = field(default_factory=list)
    unmatched_livelib: list[BookRecord] = field(default_factory=list)

    @property
    def match_rate(self) -> float:
        if not self.total_fantlab:
            return 0.0
        return len(self.matched) / self.total_fantlab * 100


def _author_overlap(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    best = 0.0
    surnames_a = {author_surname(x) for x in a}
    surnames_b = {author_surname(x) for x in b}
    if surnames_a & surnames_b:
        best = max(best, 0.95)
    for left in a:
        for right in b:
            best = max(
                best,
                fuzz.token_sort_ratio(left, right) / 100,
                fuzz.partial_ratio(left, right) / 100,
            )
    return best


def score_pair(fantlab: BookRecord, livelib: BookRecord) -> float:
    title_a = fantlab.normalized_title or normalize_title(fantlab.title)
    title_b = livelib.normalized_title or normalize_title(livelib.title)

    title_score = max(
        fuzz.token_sort_ratio(title_a, title_b) / 100,
        fuzz.token_set_ratio(title_a, title_b) / 100,
        fuzz.partial_ratio(title_a, title_b) / 100,
    )
    if title_a and title_b and (title_a in title_b or title_b in title_a):
        title_score = max(title_score, 0.92)

    author_score = _author_overlap(
        fantlab.normalized_authors or normalize_authors(fantlab.authors),
        livelib.normalized_authors or normalize_authors(livelib.authors),
    )

    if not fantlab.authors or not livelib.authors:
        return title_score

    if author_score < 0.5:
        return title_score * 0.4

    return title_score * 0.6 + author_score * 0.4


def find_best_match(
    fantlab: BookRecord,
    candidates: list[BookRecord],
    threshold: float = MATCH_THRESHOLD,
) -> MatchResult | None:
    best: BookRecord | None = None
    best_score = 0.0
    for candidate in candidates:
        score = score_pair(fantlab, candidate)
        if score > best_score:
            best_score = score
            best = candidate
    if best and best_score >= threshold:
        return MatchResult(
            fantlab=fantlab,
            livelib=best,
            method="exact" if best_score >= 0.97 else "fuzzy",
            score=best_score,
            matched=True,
        )
    return None


def match_books(
    fantlab_books: list[BookRecord],
    livelib_books: list[BookRecord],
    threshold: float = MATCH_THRESHOLD,
) -> MatchReport:
    report = MatchReport(total_fantlab=len(fantlab_books), total_livelib=len(livelib_books))

    for fantlab in fantlab_books:
        fantlab.normalized_title = normalize_title(fantlab.title)
        fantlab.normalized_authors = normalize_authors(fantlab.authors)

    for book in livelib_books:
        book.normalized_title = normalize_title(book.title)
        book.normalized_authors = normalize_authors(book.authors)

    used: set[str] = set()
    for fantlab in fantlab_books:
        key = make_match_key(fantlab.title, fantlab.authors)
        pool = [b for b in livelib_books if b.external_id not in used]
        result = find_best_match(fantlab, pool, threshold)
        if result:
            used.add(result.livelib.external_id)  # type: ignore[union-attr]
            report.matched.append(result)
        else:
            report.unmatched_fantlab.append(fantlab)

    for book in livelib_books:
        if book.external_id not in used:
            report.unmatched_livelib.append(book)

    return report


def match_with_search_map(
    fantlab_books: list[BookRecord],
    search_map: dict[str, list[BookRecord]],
    livelib_pool: list[BookRecord] | None = None,
    threshold: float = MATCH_THRESHOLD,
) -> MatchReport:
    report = MatchReport(
        total_fantlab=len(fantlab_books),
        total_livelib=sum(len(v) for v in search_map.values()),
    )

    pool_by_id = {b.external_id: b for b in (livelib_pool or [])}

    for fantlab in fantlab_books:
        fantlab.normalized_title = normalize_title(fantlab.title)
        fantlab.normalized_authors = normalize_authors(fantlab.authors)

        candidates = list(search_map.get(fantlab.external_id, []))
        if livelib_pool:
            for book in livelib_pool:
                if score_pair(fantlab, book) >= 0.65:
                    candidates.append(book)

        seen: set[str] = set()
        unique: list[BookRecord] = []
        for c in candidates:
            if c.external_id not in seen:
                seen.add(c.external_id)
                unique.append(c)

        result = find_best_match(fantlab, unique, threshold)
        if result:
            report.matched.append(result)
            pool_by_id[result.livelib.external_id] = result.livelib  # type: ignore[union-attr]
        else:
            report.unmatched_fantlab.append(fantlab)

    return report
