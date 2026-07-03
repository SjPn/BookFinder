# Bookfinder — правила для агента

## Стиль ответов
- Кратко, чётко, по сути. Без разглагольствований.
- Не знаешь — пиши «не знаю», не угадывай.
- Не перегружай ответ лишними предложениями и повторами.

## Проект
- Агрегатор рейтингов книг (FantLab + LiveLib + Fantasy-Worlds).
- MVP только при склейке ≥70%.

## Стабильный парсинг (anti-block)

Все скрипты используют `RateLimitedClient` (`src/bookfinder/http_client.py`):
- задержки и jitter по хосту (`fetch_policy.py`);
- circuit breaker (`data/processed/fetch_circuit.json`);
- cookies по хосту (`data/processed/http_cookies/`);
- warmup главной страницы перед серией запросов;
- адаптивное увеличение пауз при ошибках.

Кэш-first: `stable_fetch.py` — не качаем повторно валидный HTML/JSON из `data/raw/`.

| Источник | Стратегия |
|----------|-----------|
| Fantasy-Worlds | httpx, 0.7–2.5 с между запросами, referer с `/lib/` |
| FantLab API | 3 попытки, при SSL/таймауте → HTML `/work{id}` |
| FantLab HTML | парсинг «Средняя оценка / Оценок» + жанры |
| LiveLib | httpx; при 403 → Playwright (`livelib_browser.py`); массовый поиск — `fetch_livelib_playwright.py` |

### Команды обогащения

```powershell
$env:PYTHONPATH="src"
python scripts/run_stable_enrichment.py
python scripts/run_stable_enrichment.py --skip-fb2 --skip-livelib
python scripts/fetch_fantlab_api_cache.py --retry-failed --limit 200
python scripts/fetch_livelib_playwright.py --delay 5
```

При `Circuit open` скрипт сохраняет прогресс и останавливается — перезапуск через паузу (5–10 мин для LiveLib).

### Деплой
**Основной хост — Render** (`main` → auto-deploy). Локально API/сервер не запускать — проверки и UI на Render.

На Render/VPS кроллинг надёжнее, чем с домашней сети (FantLab API часто падает по SSL с Windows).

FB2 и `data/raw/` не в git (`.gitignore`) — только на диске сервера/локально.
