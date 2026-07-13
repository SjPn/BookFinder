"""Rating validation and aggregate score from parsed source data only."""

from __future__ import annotations

import math
from typing import Any

# Minimum voter count per source before a rating is published.
MIN_VOTES: dict[str, int] = {
    "fantlab": 10,
    "livelib": 5,
    "fantasy_worlds": 10,
    "kubikus": 10,
    "bookmix": 5,
    # LoveRead "votes" were page views — not used for validation.
    "loveread": 0,
}

RATING_MAX: dict[str, float] = {
    "fantlab": 10.0,
    "livelib": 10.0,
    "fantasy_worlds": 10.0,
    "kubikus": 5.0,
    "bookmix": 5.0,
    "loveread": 5.0,
}

# LoveRead often pins a fake ceiling 5.0/5 (=10/10). Treat as missing.
LOVEREAD_MAX_TRUSTED = 4.94


def valid_rating(source: str, rating: float | None, votes: int | None) -> bool:
    if rating is None:
        return False
    try:
        rating_f = float(rating)
        votes_i = int(votes) if votes is not None else None
    except (TypeError, ValueError):
        return False
    rating_max = RATING_MAX.get(source, 10.0)
    if not (0 < rating_f <= rating_max):
        return False
    if source == "loveread":
        # Drop ceiling scores; views must not act as votes.
        return rating_f <= LOVEREAD_MAX_TRUSTED
    min_votes = MIN_VOTES.get(source, 10)
    if votes_i is None or votes_i < min_votes:
        return False
    return True


def to_percent(source: str, rating: float) -> float:
    rating_max = RATING_MAX.get(source, 10.0)
    return rating / rating_max * 100


def _source_weight(source: str, votes: int | None) -> float:
    if source == "loveread":
        # Fixed low weight — LoveRead has no reliable vote counts.
        return 1.0
    return math.log1p(votes or 1)


def aggregate_from_sources(sources: list[tuple[str, float, int | None]]) -> float | None:
    """Weighted average on 0–100 scale; only validated source ratings."""
    parts: list[tuple[float, float]] = []
    for source, rating, votes in sources:
        if not valid_rating(source, rating, votes):
            continue
        parts.append((to_percent(source, rating), _source_weight(source, votes)))
    if not parts:
        return None
    total_w = sum(weight for _, weight in parts)
    return sum(score * weight for score, weight in parts) / total_w


def clean_source_block(source: str, block: dict[str, Any] | None) -> dict[str, Any] | None:
    if not block:
        return None
    rating = block.get("rating")
    votes = block.get("votes")
    if not valid_rating(source, rating, votes):
        cleaned = {k: v for k, v in block.items() if k not in ("rating", "votes")}
        return cleaned or None
    return block


def clean_fw_block(fw: dict[str, Any] | None) -> dict[str, Any] | None:
    return clean_source_block("fantasy_worlds", fw)


def clean_fl_block(fl: dict[str, Any] | None) -> dict[str, Any] | None:
    return clean_source_block("fantlab", fl)


def clean_ll_block(ll: dict[str, Any] | None) -> dict[str, Any] | None:
    return clean_source_block("livelib", ll)


def clean_kubikus_block(block: dict[str, Any] | None) -> dict[str, Any] | None:
    return clean_source_block("kubikus", block)


def clean_bookmix_block(block: dict[str, Any] | None) -> dict[str, Any] | None:
    return clean_source_block("bookmix", block)


def clean_loveread_block(block: dict[str, Any] | None) -> dict[str, Any] | None:
    """Keep LoveRead link metadata; drop fake 5.0 scores and view-as-votes."""
    if not block:
        return None
    cleaned = dict(block)
    cleaned.pop("votes", None)  # were page views, not ratings
    rating = cleaned.get("rating")
    try:
        rating_f = float(rating) if rating is not None else None
    except (TypeError, ValueError):
        rating_f = None
    if rating_f is not None and rating_f > LOVEREAD_MAX_TRUSTED:
        cleaned.pop("rating", None)
    if cleaned.get("rating") is None:
        cleaned.pop("rating", None)
    # Keep id/url even when rating is gone.
    if not any(cleaned.get(key) for key in ("id", "url", "rating")):
        return None
    return cleaned
