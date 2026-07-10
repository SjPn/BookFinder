from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz

from bookfinder.models import BookRecord
from bookfinder.normalize import normalize_authors, normalize_title

# Near-exact only. No "18% error margin" fuzzy merges.
MATCH_THRESHOLD = 0.98
MIN_AUTHOR_SCORE = 0.98
MIN_TITLE_SCORE = 0.98


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


def _author_tokens(author: str) -> set[str]:
    # Keep 2-letter East-Asian / initial tokens ("ли", "ха"); single letters already stripped by normalize.
    return {part for part in author.split() if len(part) >= 2}


def _author_overlap(a: list[str], b: list[str]) -> float:
    """Near-exact author match. Token order does not matter (Имя Фамилия == Фамилия Имя)."""
    if not a or not b:
        return 0.0

    best = 0.0
    for left in a:
        left_tokens = _author_tokens(left)
        if not left_tokens:
            # Fallback: whole normalized string (rare initials-only names).
            left_tokens = {left} if left else set()
        for right in b:
            right_tokens = _author_tokens(right)
            if not right_tokens:
                right_tokens = {right} if right else set()
            if not left_tokens or not right_tokens:
                continue
            # Same person, possibly reversed name order.
            if left_tokens == right_tokens:
                best = max(best, 1.0)
                continue
            shared = left_tokens & right_tokens
            # Shared short first names ("ольга") are not enough — need a longer token (surname).
            strong = {token for token in shared if len(token) >= 5}
            if strong:
                best = max(best, 1.0)
                continue
            # Rare spelling variants of long surnames only.
            for l_tok in left_tokens:
                for r_tok in right_tokens:
                    if len(l_tok) < 5 or len(r_tok) < 5:
                        continue
                    ratio = fuzz.ratio(l_tok, r_tok) / 100
                    if ratio >= MIN_AUTHOR_SCORE:
                        best = max(best, ratio)
    return best


def _title_score(title_a: str, title_b: str) -> float:
    """Titles must be nearly identical. No containment / partial_ratio tricks."""
    if not title_a or not title_b:
        return 0.0
    if title_a == title_b:
        return 1.0

    sort_score = fuzz.token_sort_ratio(title_a, title_b) / 100
    ratio_score = fuzz.ratio(title_a, title_b) / 100
    return max(sort_score, ratio_score)


def score_pair(fantlab: BookRecord, livelib: BookRecord) -> float:
    title_a = fantlab.normalized_title or normalize_title(fantlab.title)
    title_b = livelib.normalized_title or normalize_title(livelib.title)
    title_score = _title_score(title_a, title_b)

    authors_a = fantlab.normalized_authors or normalize_authors(fantlab.authors)
    authors_b = livelib.normalized_authors or normalize_authors(livelib.authors)

    # No authors on either side → refuse. Better miss a link than poison a book.
    if not authors_a or not authors_b:
        return 0.0

    author_score = _author_overlap(authors_a, authors_b)
    if author_score < MIN_AUTHOR_SCORE or title_score < MIN_TITLE_SCORE:
        return 0.0

    # Both gates passed: report the weaker of the two (conservative).
    return min(title_score, author_score)


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
            method="exact" if best_score >= 0.995 else "near_exact",
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
                if score_pair(fantlab, book) >= threshold:
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
