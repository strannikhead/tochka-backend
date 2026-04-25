#!/bin/bash
set -e

echo "Waiting for PostgreSQL to be ready..."
# Convert SQLAlchemy URL to psycopg URL (remove +psycopg part if present)
PSYCOPG_URL="${DATABASE_URL/+psycopg/}"
until python -c "import psycopg; psycopg.connect('$PSYCOPG_URL')" 2>/dev/null; do
  echo "PostgreSQL is unavailable - sleeping"
  sleep 2
done

echo "PostgreSQL is up - running migrations"
cd /app/b2b
# For Alembic, add +psycopg if not present
export DATABASE_URL="${DATABASE_URL/postgresql:/postgresql+psycopg:}"
alembic upgrade head

echo "Starting application"
exec uvicorn main:app --app-dir /app/b2b/src --host 0.0.0.0 --port 8000
