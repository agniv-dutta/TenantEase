FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATABASE_URL=sqlite:////data/khata.db

COPY pyproject.toml ./
COPY app ./app
COPY tests ./tests
COPY docker-entrypoint.sh ./

RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["sh", "docker-entrypoint.sh"]
