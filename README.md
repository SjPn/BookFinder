# Bookfinder

Агрегатор рейтингов и каталог книг: **FantLab**, **LiveLib**, **Fantasy-Worlds**, **ReadRate**.

Репозиторий: [github.com/SjPn/BookFinder](https://github.com/SjPn/BookFinder)

## Быстрый старт (локально)

```bash
pip install -r requirements.txt
set PYTHONPATH=src          # Windows
# export PYTHONPATH=src     # Linux/macOS
python run.py
```

Открыть: http://127.0.0.1:8000

Каталог читается из `data/processed/expanded_works.json` (или `merged_works.json`).

## Сборка каталога

```bash
set PYTHONPATH=src
python scripts/build_merged.py
python scripts/build_expanded.py
python scripts/run_enrichment.py   # полный цикл обогащения
```

## Деплой

### Рекомендация: VPS (рядом с UA.auto / HappyLife)

| | VPS | Render |
|---|-----|--------|
| FB2 на диске (~300+ MB) | да | ограниченно |
| Фоновые краулеры | да | нет |
| Холодный старт | нет | на free tier |
| Несколько проектов на одном сервере | nginx | отдельный сервис |

**Для Bookfinder лучше VPS**: нужны локальные FB2, большой `data/` и фоновые скрипты.

```bash
# на VPS
git clone https://github.com/SjPn/BookFinder.git /opt/bookfinder
cd /opt/bookfinder
sudo bash deploy/vps-setup.sh
sudo cp deploy/nginx-bookfinder.conf /etc/nginx/sites-available/bookfinder
# отредактировать server_name, затем:
sudo ln -s /etc/nginx/sites-available/bookfinder /etc/nginx/sites-enabled/
sudo certbot --nginx -d books.yourdomain.com
sudo systemctl reload nginx
```

Порт по умолчанию: **8010** (чтобы не конфликтовать с другими проектами). FB2 копировать отдельно:

```bash
rsync -avz ./data/books/fb2/ user@vps:/opt/bookfinder/data/books/fb2/
```

### Render (демо без FB2)

1. Подключить репозиторий на [Render](https://render.com)
2. Использовать `render.yaml` или Docker
3. План **Starter** ($7/мес) — always-on; free tier засыпает
4. Локальные FB2 недоступны — скачивание через редирект на Fantasy-Worlds

## Структура

```
src/bookfinder/   — API, парсеры, matcher
web/              — UI
scripts/          — краулеры и сборка каталога
data/processed/   — JSON каталог (в git)
data/raw/         — HTML кэш (в .gitignore)
data/books/fb2/   — локальные FB2 (в .gitignore)
deploy/           — systemd + nginx для VPS
```

## API

- `GET /api/stats` — статистика
- `GET /api/top` — топ книг
- `GET /api/search?q=&genres=` — поиск
- `GET /api/download/fw/{id}` — FB2 (локально или редирект)
- `POST /api/reload` — перечитать каталог
