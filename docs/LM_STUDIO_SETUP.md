# LM Studio + Bookfinder DNA

Инструкция для ПК, где модели качаются через **LM Studio** (как на скриншоте), а не через Ollama CLI.

## Важно про модели

| Что качаете | Для ДНК |
|-------------|---------|
| **Qwen2.5-7B-Instruct** (текст) | ✅ Да — chat-модель для JSON-профиля |
| **Qwen2.5-VL-7B** (vision) | ❌ Нет — мультимодальная, для ДНК не нужна |
| **Nomic Embed Text** | ✅ Да — эмбеддинги для похожести |

Для chat лучше скачать **текстовую** `Qwen2.5-7B-Instruct`, не VL.

## 1. LM Studio

1. Скачать: https://lmstudio.ai/
2. В **Discover** загрузить:
   - `Qwen2.5-7B-Instruct` (GGUF, Q4_K_M или Q5)
   - `Nomic Embed Text v1.5`
3. **Developer** → **Local Server** → Start Server (порт `1234`)
4. Загрузить обе модели в память (chat + embedding)

## 2. Настройка проекта

```powershell
copy .env.example .env
```

В `.env`:

```
LLM_BACKEND=lmstudio
LMSTUDIO_HOST=http://127.0.0.1:1234
LMSTUDIO_CHAT_MODEL=<имя модели из LM Studio>
LMSTUDIO_EMBED_MODEL=<имя embed-модели>
```

Имена моделей смотрите в LM Studio → Loaded Models (скопируйте точное имя).

## 3. Проверка

```powershell
$env:PYTHONPATH="src"
python scripts/check_llm.py
```

Должно вернуть `"ok": true`, размерность эмбеддинга и ответ chat.

## 4. Сборка ДНК

Пилот — 50 книг с FB2:

```powershell
python scripts/build_dna.py --only-fb2 --limit 50 --delay 0.5
```

Книги с отзывами (лучше для `reviews_summary`):

```powershell
python scripts/build_dna.py --only-with-reviews --limit 100 --delay 0.5
```

Одна книга:

```powershell
python scripts/build_dna.py --work-id "fw:12345" --force
```

## 5. Рекомендации (соседи)

После накопления профилей:

```powershell
python scripts/build_dna_neighbors.py --reindex
```

Создаёт `data/processed/dna_neighbors.json` — быстрые рекомендации в API без перебора всех книг.

## 6. Результаты

| Файл | Содержимое |
|------|------------|
| `data/processed/dna/{work_id}.json` | полный профиль |
| `data/processed/dna_index.json` | лёгкий индекс для UI/API |
| `data/processed/dna_neighbors.json` | предрасчёт похожих |
| `data/processed/dna_progress.json` | прогресс батча |

## 7. API (после сборки)

```
GET /api/works/{id}/dna
GET /api/works/{id}/similar?mode=ideas
GET /api/works/{id}/similar?mode=atmosphere
GET /api/dna/modes
```

Без ДНК — `similar` работает по старому алгоритму (жанры/автор).

## 8. Деплой на Render

1. Прогнать `build_dna.py` локально
2. Закоммитить `dna_index.json` и `dna_neighbors.json`
3. Полные `dna/*.json` в git не кладём (`.gitignore`)

## 9. Ollama вместо LM Studio

Если переключитесь на Ollama CLI — см. [OLLAMA_SETUP.md](OLLAMA_SETUP.md), в `.env` поставьте `LLM_BACKEND=ollama`.

## Типичные проблемы

| Симптом | Решение |
|---------|---------|
| `Missing LM Studio models` | Запустить Local Server, загрузить модели, проверить имена в `.env` |
| JSON parse error | Уменьшить temperature; перезапустить с `--force` |
| VL-модель отвечает плохо | Заменить на текстовый Qwen2.5-7B-Instruct |
| Медленно | Q4 квантизация, GPU, `--limit 50` для пилота |
