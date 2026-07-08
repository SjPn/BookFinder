"""DNA similarity weights — how axes combine for recommendations."""

from __future__ import annotations

import math
from typing import Iterable

from bookfinder.book_dna import ALL_AXES, BookDNAProfile

# Global blend for overall DNA score (used when mode=overall).
GLOBAL_BLEND = {
    "embedding": 0.40,
    "themes": 0.20,
    "axes": 0.15,
    "reviews": 0.10,
    "author_style": 0.10,
    "genre": 0.05,
}

SIMILARITY_MODES: dict[str, dict[str, float]] = {
    "atmosphere": {
        "darkness": 2.0,
        "hope": 2.0,
        "psychology": 1.5,
        "realism": 1.0,
        "brutality": 1.5,
        "pace": 1.0,
    },
    "ideas": {
        "thinking": 2.5,
        "philosophy": 2.0,
        "science": 1.5,
        "worldbuilding": 1.0,
    },
    "emotions": {
        "hope": 2.0,
        "darkness": 2.0,
        "psychology": 2.0,
        "romance": 1.0,
        "humor": 1.0,
        "brutality": 0.5,
    },
    "dynamics": {
        "pace": 2.5,
        "action": 2.0,
        "plot_twists": 2.0,
        "survival": 1.0,
        "dialogues": 0.5,
    },
    "gameplay": {
        "construction": 2.5,
        "survival": 2.0,
        "world_exploration": 2.0,
        "character_growth": 1.5,
        "magic": 1.0,
        "science": 1.0,
    },
    "style": {
        "difficulty": 2.0,
        "dialogues": 1.5,
        "realism": 1.5,
        "pace": 1.0,
        "humor": 1.0,
    },
}

DNA_MODES = ("overall", *SIMILARITY_MODES.keys())


def _axes_dict(profile: BookDNAProfile) -> dict[str, int]:
    return profile.axes.model_dump()


def axes_similarity(
    left: BookDNAProfile,
    right: BookDNAProfile,
    mode: str = "overall",
) -> float:
    """Weighted 1 - normalized L1 distance on selected axes."""
    left_axes = _axes_dict(left)
    right_axes = _axes_dict(right)

    if mode == "overall":
        keys = ALL_AXES
        weights = {key: 1.0 for key in keys}
    else:
        spec = SIMILARITY_MODES.get(mode, SIMILARITY_MODES["atmosphere"])
        keys = [key for key in spec if key in ALL_AXES]
        weights = {key: spec[key] for key in keys}
        if not keys:
            return 0.0

    total_weight = sum(weights.values())
    if total_weight <= 0:
        return 0.0

    distance = 0.0
    for key in keys:
        delta = abs(int(left_axes.get(key, 5)) - int(right_axes.get(key, 5)))
        distance += weights[key] * (delta / 9.0)

    return max(0.0, 1.0 - distance / total_weight)


def themes_jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    a = {item.strip().casefold() for item in left if item and item.strip()}
    b = {item.strip().casefold() for item in right if item and item.strip()}
    if not a and not b:
        return 0.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_left = math.sqrt(sum(a * a for a in left))
    norm_right = math.sqrt(sum(b * b for b in right))
    if norm_left == 0 or norm_right == 0:
        return 0.0
    return dot / (norm_left * norm_right)


def reviews_similarity(left: BookDNAProfile, right: BookDNAProfile) -> float:
    left_summary = left.reviews_summary
    right_summary = right.reviews_summary
    praised = themes_jaccard(left_summary.praised, right_summary.praised)
    criticized = themes_jaccard(left_summary.criticized, right_summary.criticized)
    emotions = themes_jaccard(left_summary.emotions, right_summary.emotions)
    parts = [score for score in (praised, criticized, emotions) if score > 0]
    if not parts:
        return 0.0
    return sum(parts) / len(parts)


def genre_similarity(left_genres: set[str], right_genres: set[str]) -> float:
    if not left_genres or not right_genres:
        return 0.0
    return len(left_genres & right_genres) / len(left_genres | right_genres)


def label_similarity(left: BookDNAProfile, right: BookDNAProfile) -> float:
    fields = ("hero", "ending", "conflict", "setting", "tone", "pov")
    scores: list[float] = []
    for field in fields:
        a = getattr(left.labels, field, "").strip().casefold()
        b = getattr(right.labels, field, "").strip().casefold()
        if not a or not b:
            continue
        if a == b:
            scores.append(1.0)
        elif a in b or b in a:
            scores.append(0.75)
        else:
            scores.append(0.0)
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def combined_similarity(
    left: BookDNAProfile,
    right: BookDNAProfile,
    mode: str = "overall",
    *,
    left_genres: set[str] | None = None,
    right_genres: set[str] | None = None,
) -> float:
    """Score 0..1 for ranking recommendations."""
    if mode == "overall":
        genre_score = 0.0
        if left_genres is not None and right_genres is not None:
            genre_score = genre_similarity(left_genres, right_genres)
        parts = [
            GLOBAL_BLEND["embedding"] * cosine_similarity(left.embedding or [], right.embedding or []),
            GLOBAL_BLEND["themes"] * themes_jaccard(left.themes, right.themes),
            GLOBAL_BLEND["axes"] * axes_similarity(left, right, mode="overall"),
            GLOBAL_BLEND["reviews"] * reviews_similarity(left, right),
            GLOBAL_BLEND["genre"] * genre_score,
        ]
        return sum(parts)

    axis_score = axes_similarity(left, right, mode=mode)
    theme_score = themes_jaccard(left.themes, right.themes)
    embed_score = cosine_similarity(left.embedding or [], right.embedding or [])
    label_score = label_similarity(left, right)

    if mode == "ideas":
        return 0.45 * embed_score + 0.30 * theme_score + 0.25 * axis_score
    if mode == "atmosphere":
        return 0.35 * axis_score + 0.35 * embed_score + 0.20 * label_score + 0.10 * theme_score
    if mode == "emotions":
        return 0.40 * axis_score + 0.30 * embed_score + 0.20 * theme_score + 0.10 * label_score
    if mode == "dynamics":
        return 0.55 * axis_score + 0.25 * embed_score + 0.20 * theme_score
    if mode == "gameplay":
        return 0.60 * axis_score + 0.25 * theme_score + 0.15 * embed_score
    if mode == "style":
        return 0.50 * axis_score + 0.30 * embed_score + 0.20 * label_score

    return 0.5 * axis_score + 0.3 * embed_score + 0.2 * theme_score
