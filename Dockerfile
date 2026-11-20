FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run injects PORT; default 8000 for local/docker-compose
ENV PORT=8000
ENV HOST=0.0.0.0
EXPOSE 8000

CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
