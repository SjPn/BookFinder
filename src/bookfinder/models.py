from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class BookRecord:
    source: str
    external_id: str
    title: str
    authors: list[str]
    rating: float | None = None
    rating_max: float = 10.0
    vote_count: int | None = None
    rank: int | None = None
    work_type: str | None = None
    year: int | None = None
    url: str | None = None
    genres: list[str] = field(default_factory=list)
    normalized_title: str = ""
    normalized_authors: list[str] = field(default_factory=list)

    @property
    def normalized_score(self) -> float | None:
        if self.rating is None:
            return None
        return (self.rating / self.rating_max) * 100
