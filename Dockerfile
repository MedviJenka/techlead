FROM python:3.13-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.11.33 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

RUN groupadd --system app && useradd --system --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /srv

COPY pyproject.toml uv.lock ./


# AI worker (`python -m app.worker`): the API's dependencies plus CrewAI (the `ai` group). Runs NewLeadFlow on
# queued analysis jobs; run as many replicas as you like.
FROM base AS worker

RUN uv sync --frozen --no-default-groups --group ai --no-install-project

COPY settings.py ./
COPY ai ./ai
COPY app ./app

# CrewAI and agent memory write under $HOME and AI_MEMORY_CACHE_DIR; the code itself stays read-only.
ENV HOME=/tmp \
    AI_MEMORY_CACHE_DIR=/tmp/ai_memory

USER app

CMD ["python", "-m", "app.worker"]


# API (default target): no CrewAI. AI runs never execute inside a request; they are queued for the worker.
FROM base AS api

RUN uv sync --frozen --no-default-groups --no-install-project

COPY settings.py ./
COPY ai ./ai
COPY app ./app

# Code and /opt/venv stay root-owned (world-readable); the app only needs to read them.
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
