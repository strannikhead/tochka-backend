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
COPY b2c/pyproject.toml ./b2c/

RUN uv sync --frozen --package b2c-service --no-dev

COPY b2c/src ./b2c/src

EXPOSE 8000
CMD ["uvicorn", "main:app", "--app-dir", "b2c/src", "--host", "0.0.0.0", "--port", "8000"]
