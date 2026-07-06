FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY web/ web/
COPY run.py .
COPY data/processed/catalog.db.gz data/processed/catalog.db.gz
COPY data/processed/genres.json data/processed/genres.json
COPY data/processed/reviews/ data/processed/reviews/
COPY data/processed/user_ratings.json data/processed/user_ratings.json

RUN python -c "from pathlib import Path; from bookfinder.catalog_db import ensure_catalog_db; ensure_catalog_db(Path('data/processed'))"

ENV PYTHONPATH=/app/src
ENV HOST=0.0.0.0
ENV PORT=8000

EXPOSE 8000

CMD uvicorn bookfinder.api:app --host ${HOST} --port ${PORT} --workers 1
