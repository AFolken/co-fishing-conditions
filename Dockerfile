FROM python:3.12-slim

WORKDIR /app

# Install system deps for psycopg2 and lxml
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq-dev gcc libxml2-dev libxslt1-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir ".[app]"

ENV PYTHONPATH=/app/src
EXPOSE 8501
