FROM python:3.14-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY shared/pyproject.toml ./shared/
COPY shared/src ./shared/src
COPY moderation/pyproject.toml ./moderation/

RUN uv sync --frozen --package moderation-service --no-dev

COPY moderation/src ./moderation/src

EXPOSE 8000
CMD ["uvicorn", "main:app", "--app-dir", "moderation/src", "--host", "0.0.0.0", "--port", "8000"]
