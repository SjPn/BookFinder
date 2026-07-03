FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY web/ web/
COPY data/processed/ data/processed/
COPY run.py .

ENV PYTHONPATH=/app/src
ENV HOST=0.0.0.0
ENV PORT=8000

EXPOSE 8000

CMD uvicorn bookfinder.api:app --host ${HOST} --port ${PORT}
