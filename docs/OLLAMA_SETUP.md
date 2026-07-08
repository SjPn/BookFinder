# Перенос Bookfinder на ПК с Ollama

Инструкция для машины, где будет **локальная Ollama** и пайплайн **ДНК книги**.  
Render остаётся для веб-каталога; Ollama и FB2 — только локально.

## 1. Что скопировать

Минимальный набор:

```
Bookfinder/
├── src/
├── scripts/
├── web/
├── run.py
├── requirements.txt
├── .env.example  → скопировать в .env
└── data/
    └── processed/
        ├── catalog.db.gz      # или catalog.db после распаковки
        ├── genres.json
        ├── reviews/           # опционально, улучшает ДНК
        └── expanded_works.json  # fallback, если нет catalog.db
```

Рекомендуется также (тяжёлые, но дают лучшую ДНК):

```
data/books/fb2/          # ~22k+ архивов .fb2.zip
data/raw/fw_books/       # HTML для отзывов FW (опционально)
```

**Не обязательно на Ollama-ПК:** `data/raw/` целиком, логи, `catalog.db` в git (есть `.gz`).

### Быстрый перенос

```powershell
# На старом ПК — архив проекта без .venv
tar -czf bookfinder-ollama.tgz --exclude=.venv --exclude=__pycache__ Bookfinder

# На новом ПК
tar -xzf bookfinder-ollama.tgz
cd Bookfinder
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

## 2. Установка Ollama

1. Скачать: https://ollama.com/download  
2. Запустить Ollama (должен слушать `http://127.0.0.1:11434`)
3. В `.env` указать `LLM_BACKEND=ollama`
4. Скачать модели:

```powershell
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

Альтернативы:
- chat: `llama3.1:8b`, `mistral`
- embed: `mxbai-embed-large`

Задать в `.env`:

```
OLLAMA_CHAT_MODEL=qwen2.5:7b
OLLAMA_EMBED_MODEL=nomic-embed-text
```

## 3. Подготовка каталога

```powershell
$env:PYTHONPATH="src"
# если есть только catalog.db.gz:
python -c "from pathlib import Path; from bookfinder.catalog_db import ensure_catalog_db; ensure_catalog_db(Path('data/processed'))"

# проверка LLM (Ollama или LM Studio)
python scripts/check_llm.py
```

## 4. Сборка ДНК книги

Пилот (50 книг с FB2):

```powershell
$env:PYTHONPATH="src"
python scripts/build_dna.py --only-fb2 --limit 50 --delay 0.5
```

Одна книга:

```powershell
python scripts/build_dna.py --work-id "fw:12345" --force
```

Ночной батч (все с FB2):

```powershell
python scripts/build_dna.py --only-fb2 --delay 0.3
```

Результаты:

| Путь | Содержимое |
|------|------------|
| `data/processed/dna/{work_id}.json` | полный профиль ДНК |
| `data/processed/dna_index.json` | сводный индекс для UI/API |
| `data/processed/dna_progress.json` | статус обработки |

## 5. Что получаем на каждую книгу

- **22 оси** (1–10): сюжет + опыт чтения  
- **labels**: герой, конфликт, сеттинг, финал, тон, POV  
- **themes**: ключевые темы  
- **ai_summary**: AI-аннотация (2–4 предложения)  
- **ai_tagline**: короткий хук  
- **embedding**: вектор для похожести по смыслу  
- **reviews_summary**: агрегат отзывов  

Подробнее о параметрах и мэтчинге: [DNA_SCHEMA.md](DNA_SCHEMA.md)

## 6. Деплой ДНК на Render (позже)

1. Прогнать `build_dna.py` локально  
2. Закоммитить `dna_index.json` (лёгкий) или залить артефакты отдельно  
3. Подключить API `similar?mode=ideas|atmosphere|...` (фаза 1 UI)

Полные `dna/*.json` (~40k) в git не кладём — только индекс или отдельное хранилище.

## 7. Типичные проблемы

| Симптом | Решение |
|---------|---------|
| `Missing Ollama models` | `ollama pull ...` |
| `catalog.db not found` | `export_runtime_catalog.py` или распаковать `.gz` |
| Медленно | `--only-fb2 --limit 100`, меньшая модель, GPU |
| JSON parse error | `--force` перезапуск; снизить temperature в коде |
| OOM Ollama | модель 3B/7B вместо 13B+ |

## 8. Рекомендуемые характеристики ПК

| | Минимум | Комфорт |
|---|---------|---------|
| RAM | 16 GB | 32 GB |
| GPU | — | 8+ GB VRAM |
| Диск | 50 GB свободно | 200 GB (FB2 + модели) |
