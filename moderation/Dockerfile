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

# Copy Alembic migrations
COPY moderation/alembic.ini ./moderation/
COPY moderation/alembic ./moderation/alembic

COPY moderation/src ./moderation/src

# Copy entrypoint script
COPY moderation/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
