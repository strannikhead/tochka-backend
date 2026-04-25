#!/bin/bash
set -e

echo "Waiting for PostgreSQL to be ready..."
until python -c "import psycopg; psycopg.connect('$DATABASE_URL')" 2>/dev/null; do
  echo "PostgreSQL is unavailable - sleeping"
  sleep 2
done

echo "PostgreSQL is up - running migrations"
cd /app/b2c
alembic upgrade head

echo "Starting application"
exec uvicorn main:app --app-dir /app/b2c/src --host 0.0.0.0 --port 8000
