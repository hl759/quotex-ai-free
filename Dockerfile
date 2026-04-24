FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8000

CMD gunicorn --workers 1 --threads 2 \
    --bind 0.0.0.0:$PORT \
    --timeout 300 --keep-alive 5 \
    --max-requests 200 --max-requests-jitter 20 \
    app:app
