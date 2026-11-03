# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.3 /uv /bin/uv

WORKDIR /app

# 1) Só as dependências, com um pacote vazio, para aproveitar o cache de build.
COPY backend/pyproject.toml backend/README.md ./backend/
RUN --mount=type=cache,target=/root/.cache/uv \
    mkdir -p backend/roadie && touch backend/roadie/__init__.py \
    && uv pip install --system ./backend \
    && rm -rf backend/roadie

# 2) Código e dados.
COPY backend/ ./backend/
COPY data/ ./data/
RUN --mount=type=cache,target=/root/.cache/uv uv pip install --system --no-deps ./backend

ENV DATA_DIR=/app/data
WORKDIR /app/backend
EXPOSE 8000

ENTRYPOINT ["/app/backend/docker-entrypoint.sh"]
CMD ["uvicorn", "roadie.main:app", "--host", "0.0.0.0", "--port", "8000"]
