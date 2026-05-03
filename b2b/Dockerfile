FROM python:3.14-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Minimal workspace: only what b2b-service actually needs
COPY pyproject.toml uv.lock ./
COPY shared/pyproject.toml ./shared/
COPY shared/src ./shared/src
COPY b2b/pyproject.toml ./b2b/

# Install deps + shared into /app/.venv
RUN uv sync --frozen --package b2b-service --no-dev

# Copy Alembic migrations
COPY b2b/alembic.ini ./b2b/
COPY b2b/alembic ./b2b/alembic

# Service code last for better layer caching
COPY b2b/src ./b2b/src

# Copy entrypoint script
COPY b2b/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
