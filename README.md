# Bookfinder

Агрегатор рейтингов и каталог книг: **FantLab**, **LiveLib**, **Fantasy-Worlds**, **ReadRate**, **Kubikus**, **BookMix**.

## Быстрый старт

```bash
pip install -r requirements.txt
export PYTHONPATH=src   # Windows: set PYTHONPATH=src
python run.py
```

Каталог: `data/processed/expanded_works.json`.

## Сборка каталога

```bash
export PYTHONPATH=src
python scripts/build_merged.py
python scripts/build_expanded.py
python scripts/embed_work_reviews.py
```

## Структура

```
src/bookfinder/   — API, парсеры, matcher
web/              — UI
scripts/          — краулеры и сборка каталога
data/processed/   — JSON каталог
```

`data/raw/` и `data/books/fb2/` в `.gitignore` — не коммитятся.

## Планы

[docs/PLANS.md](docs/PLANS.md) — дорожная карта, в т.ч. **«ДНК книги»** (профиль книги, рекомендации, локальная Ollama).
