"""Book DNA schema — axes, labels, and prompt contract for Ollama."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

DNA_VERSION = 1
PROMPT_VERSION = "dna-v1"

# Numeric axes 1–10. Keys are stable API identifiers (English).
CONTENT_AXES = (
    "character_growth",
    "world_exploration",
    "politics",
    "romance",
    "humor",
    "action",
    "brutality",
    "science",
    "magic",
    "survival",
    "construction",
)

EXPERIENCE_AXES = (
    "thinking",
    "philosophy",
    "darkness",
    "hope",
    "psychology",
    "worldbuilding",
    "realism",
    "pace",
    "difficulty",
    "dialogues",
    "plot_twists",
)

ALL_AXES = CONTENT_AXES + EXPERIENCE_AXES

AXIS_LABELS_RU: dict[str, str] = {
    "character_growth": "Развитие героя",
    "world_exploration": "Исследование мира",
    "politics": "Политика",
    "romance": "Романтика",
    "humor": "Юмор",
    "action": "Экшен",
    "brutality": "Жестокость",
    "science": "Наука",
    "magic": "Магия",
    "survival": "Выживание",
    "construction": "Строительство",
    "thinking": "Заставляет думать",
    "philosophy": "Философия",
    "darkness": "Мрачность",
    "hope": "Надежда",
    "psychology": "Психология",
    "worldbuilding": "Проработка мира",
    "realism": "Реализм",
    "pace": "Темп",
    "difficulty": "Сложность языка",
    "dialogues": "Диалоги",
    "plot_twists": "Неожиданные повороты",
}


class DNAAxes(BaseModel):
    character_growth: int = Field(ge=1, le=10, default=5)
    world_exploration: int = Field(ge=1, le=10, default=5)
    politics: int = Field(ge=1, le=10, default=5)
    romance: int = Field(ge=1, le=10, default=5)
    humor: int = Field(ge=1, le=10, default=5)
    action: int = Field(ge=1, le=10, default=5)
    brutality: int = Field(ge=1, le=10, default=5)
    science: int = Field(ge=1, le=10, default=5)
    magic: int = Field(ge=1, le=10, default=5)
    survival: int = Field(ge=1, le=10, default=5)
    construction: int = Field(ge=1, le=10, default=5)
    thinking: int = Field(ge=1, le=10, default=5)
    philosophy: int = Field(ge=1, le=10, default=5)
    darkness: int = Field(ge=1, le=10, default=5)
    hope: int = Field(ge=1, le=10, default=5)
    psychology: int = Field(ge=1, le=10, default=5)
    worldbuilding: int = Field(ge=1, le=10, default=5)
    realism: int = Field(ge=1, le=10, default=5)
    pace: int = Field(ge=1, le=10, default=5)
    difficulty: int = Field(ge=1, le=10, default=5)
    dialogues: int = Field(ge=1, le=10, default=5)
    plot_twists: int = Field(ge=1, le=10, default=5)


class DNALabels(BaseModel):
    hero: str = ""
    ending: str = ""
    conflict: str = ""
    setting: str = ""
    tone: str = ""
    pov: str = ""


class DNAReviewsSummary(BaseModel):
    praised: list[str] = Field(default_factory=list)
    criticized: list[str] = Field(default_factory=list)
    emotions: list[str] = Field(default_factory=list)


class DNASources(BaseModel):
    annotation: float = Field(ge=0.0, le=1.0, default=0.0)
    reviews: float = Field(ge=0.0, le=1.0, default=0.0)
    text: float = Field(ge=0.0, le=1.0, default=0.0)


class BookDNAProfile(BaseModel):
    work_id: str
    version: int = DNA_VERSION
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    axes: DNAAxes
    labels: DNALabels = Field(default_factory=DNALabels)
    themes: list[str] = Field(default_factory=list)
    ai_tagline: str = ""
    ai_summary: str = ""
    reviews_summary: DNAReviewsSummary = Field(default_factory=DNAReviewsSummary)
    sources: DNASources = Field(default_factory=DNASources)
    embedding: list[float] | None = None
    embedding_model: str = ""
    chat_model: str = ""
    prompt_version: str = PROMPT_VERSION
    updated_at: str = ""

    @field_validator("themes", mode="before")
    @classmethod
    def _themes_to_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_dna_prompt(
    *,
    title: str,
    authors: list[str],
    genres: list[str],
    catalog_description: str,
    review_snippets: list[str],
    text_sample: str,
) -> str:
    authors_text = ", ".join(authors) if authors else "неизвестен"
    genres_text = ", ".join(genres[:12]) if genres else "не указаны"
    reviews_block = "\n".join(f"- {line}" for line in review_snippets[:8]) or "нет"
    text_block = text_sample.strip() or "нет фрагмента текста"

    return f"""Ты аналитик художественной литературы. По данным о книге построй профиль «ДНК книги».

КНИГА: «{title}»
АВТОР(Ы): {authors_text}
ЖАНРЫ (каталог, вспомогательно): {genres_text}

АННОТАЦИЯ ИЗ КАТАЛОГА:
{catalog_description or "нет"}

ОТЗЫВЫ ЧИТАТЕЛЕЙ (выдержки):
{reviews_block}

ФРАГМЕНТ ТЕКСТА (начало / середина / конец):
{text_block[:8000]}

ЗАДАЧА:
1. Оцени ВСЕ оси шкалой 1–10 (целые числа).
2. Заполни labels короткими фразами на русском.
3. themes — 3–8 ключевых тем (короткие фразы).
4. ai_tagline — одна цепляющая фраза о книге (до 120 символов).
5. ai_summary — аннотация 2–4 предложения: о чём книга, тон, для кого; без спойлеров финала.
6. reviews_summary — что хвалят / ругают / эмоции после прочтения.

Оси (1 = почти нет, 10 = очень сильно):
Сюжет: character_growth, world_exploration, politics, romance, humor, action, brutality, science, magic, survival, construction
Опыт: thinking, philosophy, darkness, hope, psychology, worldbuilding, realism, pace, difficulty, dialogues, plot_twists

labels: hero (тип героя), ending (open|bittersweet|happy|tragic|ambiguous), conflict, setting, tone, pov

Ответь ТОЛЬКО валидным JSON без markdown:
{{
  "axes": {{ ... все 22 оси ... }},
  "labels": {{ "hero": "", "ending": "", "conflict": "", "setting": "", "tone": "", "pov": "" }},
  "themes": ["..."],
  "ai_tagline": "...",
  "ai_summary": "...",
  "reviews_summary": {{ "praised": [], "criticized": [], "emotions": [] }}
}}"""


def embedding_text(profile: BookDNAProfile) -> str:
    summary = profile.reviews_summary
    parts = [
        profile.title,
        ", ".join(profile.authors),
        profile.ai_tagline,
        profile.ai_summary,
        ", ".join(profile.themes),
        profile.labels.hero,
        profile.labels.conflict,
        profile.labels.setting,
        profile.labels.tone,
        ", ".join(summary.praised),
        ", ".join(summary.criticized),
        ", ".join(summary.emotions),
    ]
    return "\n".join(part for part in parts if part).strip()
