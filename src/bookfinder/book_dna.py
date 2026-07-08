"""Book DNA schema — axes, labels, and prompt contract for Ollama."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

DNA_VERSION = 1
PROMPT_VERSION = "dna-v2"

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

AXIS_HINTS_RU: dict[str, str] = {
    "character_growth": "Насколько герой меняется и растёт за книгу.",
    "world_exploration": "Открытие новых мест, культур и тайн мира.",
    "politics": "Интриги, власть, фракции и большие решения.",
    "romance": "Романтическая линия и чувства между персонажами.",
    "humor": "Шутки, ирония и лёгкость подачи.",
    "action": "Погони, драки, опасные сцены и динамика.",
    "brutality": "Жестокость, насилие и мрачные сцены.",
    "science": "Научные идеи, технологии, исследования.",
    "magic": "Магия, чудеса и сверхъестественное.",
    "survival": "Борьба за жизнь, риск и напряжение выживания.",
    "construction": "Строительство базы, империи или долгих проектов.",
    "thinking": "Заставляет задуматься и анализировать.",
    "philosophy": "Философские вопросы и смыслы.",
    "darkness": "Мрачная, тяжёлая атмосфера.",
    "hope": "Светлые ноты, вера в лучшее.",
    "psychology": "Внутренний мир героев и мотивации.",
    "worldbuilding": "Проработанность мира, правил и деталей.",
    "realism": "Правдоподобие событий и поведения.",
    "pace": "Скорость развития сюжета.",
    "difficulty": "Сложность языка и стиля.",
    "dialogues": "Важность и качество диалогов.",
    "plot_twists": "Неожиданные повороты сюжета.",
}

AXIS_SIMILAR_MODE: dict[str, str] = {
    "character_growth": "gameplay",
    "world_exploration": "gameplay",
    "politics": "ideas",
    "romance": "emotions",
    "humor": "style",
    "action": "dynamics",
    "brutality": "atmosphere",
    "science": "ideas",
    "magic": "gameplay",
    "survival": "dynamics",
    "construction": "gameplay",
    "thinking": "ideas",
    "philosophy": "ideas",
    "darkness": "atmosphere",
    "hope": "emotions",
    "psychology": "emotions",
    "worldbuilding": "atmosphere",
    "realism": "style",
    "pace": "dynamics",
    "difficulty": "style",
    "dialogues": "style",
    "plot_twists": "dynamics",
}

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
    reader_badge: str = ""
    ai_overview: list[str] = Field(default_factory=list)
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

    @field_validator("ai_overview", mode="before")
    @classmethod
    def _overview_to_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            parts = [part.strip() for part in value.split("\n\n") if part.strip()]
            if not parts and value.strip():
                parts = [line.strip() for line in value.splitlines() if line.strip()]
            return parts[:5]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()][:5]
        return []


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def derive_reader_badge(axes: dict[str, int] | None, genres: list[str] | None = None) -> str:
    values = axes or {}
    genre_text = " ".join(genres or []).casefold()

    if int(values.get("romance", 0)) >= 8:
        if int(values.get("pace", 0)) >= 7:
            return "Горячая романтика"
        return "Романтическая история"
    if int(values.get("humor", 0)) >= 8:
        return "Лёгкое чтение"
    if int(values.get("action", 0)) >= 8 and int(values.get("pace", 0)) >= 7:
        return "Динамичный экшен"
    if int(values.get("thinking", 0)) >= 8 or int(values.get("philosophy", 0)) >= 8:
        return "Заставляет думать"
    if int(values.get("darkness", 0)) >= 8:
        return "Мрачная атмосфера"
    if int(values.get("worldbuilding", 0)) >= 8 or int(values.get("magic", 0)) >= 8:
        return "Богатый мир"
    if "любов" in genre_text or "роман" in genre_text:
        return "Для любителей романтики"
    if int(values.get("pace", 0)) <= 4 and int(values.get("difficulty", 0)) >= 7:
        return "Вдумчивое чтение"

    top_key = max(values, key=lambda key: int(values.get(key, 0)), default="")
    top_value = int(values.get(top_key, 0)) if top_key else 0
    if top_key and top_value >= 7:
        label = AXIS_LABELS_RU.get(top_key, top_key).lower()
        return f"Сильная {label}"
    return "Для спокойного вечера"


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
6. reader_badge — короткий чип для читателя (до 40 символов), например «Горячая романтика» или «Лёгкое чтение».
7. ai_overview — краткий обзор/пересказ книги: 2–5 абзацев, по 2–4 предложения в каждом; без спойлеров финала и ключевых поворотов.
8. reviews_summary — что хвалят / ругают / эмоции после прочтения.

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
  "reader_badge": "...",
  "ai_overview": ["абзац 1", "абзац 2"],
  "reviews_summary": {{ "praised": [], "criticized": [], "emotions": [] }}
}}"""


def build_overview_prompt(
    *,
    title: str,
    authors: list[str],
    genres: list[str],
    ai_tagline: str,
    ai_summary: str,
    themes: list[str],
    catalog_description: str,
) -> str:
    authors_text = ", ".join(authors) if authors else "неизвестен"
    genres_text = ", ".join(genres[:12]) if genres else "не указаны"
    themes_text = ", ".join(themes[:8]) if themes else "нет"

    return f"""Ты литературный редактор. По данным о книге напиши краткий обзор для читателя.

КНИГА: «{title}»
АВТОР(Ы): {authors_text}
ЖАНРЫ: {genres_text}
ТЕМЫ: {themes_text}
TAGLINE: {ai_tagline or "нет"}
КРАТКО: {ai_summary or "нет"}

АННОТАЦИЯ:
{catalog_description or "нет"}

ЗАДАЧА:
1. reader_badge — короткий чип (до 40 символов), например «Горячая романтика».
2. ai_overview — 2–5 абзацев пересказа/обзора по 2–4 предложения; без спойлеров финала.

Ответь ТОЛЬКО JSON:
{{
  "reader_badge": "...",
  "ai_overview": ["абзац 1", "абзац 2"]
}}"""


def embedding_text(profile: BookDNAProfile) -> str:
    summary = profile.reviews_summary
    parts = [
        profile.title,
        ", ".join(profile.authors),
        profile.ai_tagline,
        profile.ai_summary,
        profile.reader_badge,
        "\n".join(profile.ai_overview),
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
