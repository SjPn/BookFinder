# Bookfinder

Агрегатор рейтингов и каталог книг: **FantLab**, **LiveLib**, **Fantasy-Worlds**, **ReadRate**, **Kubikus**, **BookMix**.

## Быстрый старт

```bash
pip install -r requirements.txt
export PYTHONPATH=src   # Windows: set PYTHONPATH=src
python run.py
```

Каталог в проде: **`data/processed/catalog.db`** (SQLite). В git — **`catalog.db.gz`** (~38 MB); при старте распаковывается автоматически.

## Сборка каталога

```bash
export PYTHONPATH=src
python scripts/build_merged.py
python scripts/build_expanded.py
python scripts/export_runtime_catalog.py
python scripts/embed_work_reviews.py
```

## Структура

```
src/bookfinder/   — API, парсеры, matcher
web/              — UI
scripts/          — краулеры и сборка каталога
data/processed/   — catalog.db, genres.json, отзывы
```

`data/raw/` и `data/books/fb2/` в `.gitignore` — не коммитятся.

## Планы

- [docs/PLANS.md](docs/PLANS.md) — дорожная карта, **«ДНК книги»**
- [docs/OLLAMA_SETUP.md](docs/OLLAMA_SETUP.md) — перенос на ПК с Ollama
- [docs/LM_STUDIO_SETUP.md](docs/LM_STUDIO_SETUP.md) — LM Studio (локальный LLM)
- [docs/DNA_SCHEMA.md](docs/DNA_SCHEMA.md) — оси, мэтчинг, рекомендации

### ДНК (Ollama, локально)

```bash
python scripts/check_ollama.py
python scripts/build_dna.py --only-fb2 --limit 50
```
