# Схема ДНК книги и логика похожести

Документ для разработки рекомендаций: **какие параметры измеряем** и **как из них собирать мэтчинг**.

## Три слоя профиля

```
┌─────────────────────────────────────────────────────────┐
│ 1. ЧИСЛА (axes)     → фильтры, сортировка, расстояние │
│ 2. КАТЕГОРИИ (labels) → герой, конфликт, финал, тон    │
│ 3. СМЫСЛ (themes + embedding + ai_summary) → идеи, vibe │
└─────────────────────────────────────────────────────────┘
```

Похожесть **никогда не сводится к одному числу** — только к режимам (`atmosphere`, `ideas`, …).

---

## Оси: зачем каждая группа

### Сюжет и содержание (что происходит)

| Ось | Для фильтров | Для рекомендаций |
|-----|--------------|------------------|
| `character_growth` | «книги про взросление» | gameplay, overall |
| `world_exploration` | исследование, карта | gameplay, ideas |
| `politics` | интриги, власть | ideas |
| `romance` | любовная линия | emotions |
| `humor` | комедия | style, emotions |
| `action` | драйв | dynamics |
| `brutality` | жестокость | atmosphere |
| `science` | hard SF | ideas |
| `magic` | фэнтези-система | gameplay, ideas |
| `survival` | выживание | gameplay, dynamics |
| `construction` | база, крафт, litRPG | gameplay |

### Опыт чтения (как ощущается)

| Ось | Для фильтров | Для рекомендаций |
|-----|--------------|------------------|
| `thinking` | «заставляет думать» | ideas |
| `philosophy` | глубина вопросов | ideas |
| `darkness` / `hope` | тон | atmosphere, emotions |
| `psychology` | внутренний мир | atmosphere, emotions |
| `worldbuilding` | глубина лора | ideas, atmosphere |
| `realism` | правдоподобие | style, atmosphere |
| `pace` | темп | dynamics, atmosphere |
| `difficulty` | сложность языка | style |
| `dialogues` | разговорность | style |
| `plot_twists` | непредсказуемость | dynamics |

**Важно:** `brutality` ≠ `darkness`, `world_exploration` ≠ `worldbuilding`.

---

## Labels (категории)

| Поле | Пример | Использование |
|------|--------|---------------|
| `hero` | «одинокий интеллектуал» | фильтр «сильный герой», label match |
| `ending` | open / tragic / happy | спойлер-free группировка |
| `conflict` | «человек vs система» | ideas, recommendations |
| `setting` | «ближайшее будущее» | ideas, atmosphere |
| `tone` | «мрачный, но жизнеутверждающий» | atmosphere |
| `pov` | «от первого лица» | style |

---

## AI-описание

| Поле | Назначение |
|------|------------|
| `ai_tagline` | карточка в списке, один клик — суть |
| `ai_summary` | страница книги, если нет аннотации; вход в embedding |
| `embedding` | cosine similarity — «похожи по смыслу» |

Текст для эмбеддинга: title + authors + tagline + summary + themes + labels.

---

## Режимы похожести

Реализация: `src/bookfinder/dna_similarity.py`

| Режим | Что ищем | Основные сигналы |
|-------|----------|------------------|
| `atmosphere` | тот же вайб | darkness, hope, psychology, embedding, labels.tone |
| `ideas` | те же темы | thinking, philosophy, themes, embedding |
| `emotions` | те же чувства | hope, darkness, psychology, romance |
| `dynamics` | тот же темп | pace, action, plot_twists |
| `gameplay` | litRPG / выживание | construction, survival, exploration, magic |
| `style` | тот же стиль прозы | difficulty, dialogues, realism |
| `overall` | общая похожесть | 40% embed + 20% themes + 15% axes + … |

### Формула overall (стартовая)

- 40% — cosine(embedding)
- 20% — Jaccard(themes)
- 15% — distance(axes)
- 10% — reviews (фаза 2)
- 10% — стиль автора (фаза 4)
- 5% — жанр (вспомогательно)

---

## Источники и уверенность (`sources`)

| Ключ | Значение |
|------|----------|
| `annotation` | есть описание из каталога |
| `reviews` | есть отзывы |
| `text` | есть фрагмент FB2 |

Низкая уверенность → показывать в UI «профиль предварительный».

---

## Версионирование

- `version` — схема JSON (ломающие изменения)
- `prompt_version` — промпт Ollama (`dna-v1`)
- `chat_model` / `embedding_model` — для пересборки при смене модели

При смене `prompt_version` — `--force` на всём каталоге.

---

## Файлы в проекте

| Модуль | Роль |
|--------|------|
| `book_dna.py` | Pydantic-схема, промпт |
| `ollama_client.py` | HTTP к Ollama |
| `fb2_text.py` | выборка текста из FB2 |
| `dna_store.py` | сохранение JSON |
| `dna_similarity.py` | веса похожести |
| `scripts/build_dna.py` | батч-обработка |
| `scripts/check_ollama.py` | проверка окружения |
