# Tochka Backend

Монорепозиторий бэкенда NeoMarket: три независимых сервиса, общая библиотека, единый `uv.lock` на весь workspace.

[![API Docs](https://img.shields.io/badge/API%20Docs-Swagger%20UI-85ea2d?logo=swagger)](https://urfu2026-neomarket.github.io/neomarket-protocols/)

## Структура

```
.
├── b2b/                  # Seller Cabinet (товары, SKU, накладные)
│   ├── openapi.yaml
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── src/
│       ├── main.py
│       └── api/{products,skus,invoices}/
├── b2c/                  # Каталог, корзина, избранное, главная
│   ├── catalog/openapi.yaml
│   ├── cart/openapi.yaml
│   ├── orders/openapi.yaml
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── src/
│       ├── main.py
│       └── api/{products,categories,catalog,cart,favorites,home}/
├── moderation/           # Модерация карточек товаров
│   ├── openapi.yaml
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── src/
│       ├── main.py
│       └── api/{product_moderation,blocking_reasons}/
├── shared/               # Общая python-библиотека (модели, JWT, HTTP-клиенты)
│   ├── pyproject.toml
│   └── src/shared/
├── docs/, forge/         # Документация и proto-описания
├── pyproject.toml        # корень uv-workspace + dev-инструменты
├── uv.lock
├── docker-compose.yml
└── .pre-commit-config.yaml
```

Сервисы `b2b`, `b2c`, `moderation` деплоятся независимо. В рантайме общаются через HTTP (B2C → B2B за ценами/наличием).

## Стек

**Runtime:** Python 3.14, [uv](https://docs.astral.sh/uv/) (пакетный менеджер + workspace).

**Prod-зависимости** (в каждом сервисе):
- `fastapi` + `uvicorn[standard]` — ASGI-приложение и сервер
- `pydantic` + `pydantic-settings` — модели и конфиг из env
- `sqlalchemy[asyncio]` + `alembic` — ORM и миграции
- `psycopg[binary,pool]` — async-драйвер PostgreSQL
- `httpx` — async HTTP-клиент для inter-service вызовов
- `pyjwt` — верификация JWT из `Authorization: Bearer`
- `redis` — кэширование
- `shared` — общая библиотека (workspace-dep)

**Dev-инструменты** (в корневом `pyproject.toml`, группа `dev`):
- `ruff` — линтер и форматтер
- `mypy` — статическая типизация
- `pytest`, `pytest-asyncio`, `pytest-cov` — тесты
- `schemathesis` — property-based contract-тесты по OpenAPI-спекам
- `pre-commit` — git-хуки

## Установка

```bash
# uv сам поставит Python 3.14, если нет
uv sync --all-packages

# git-хуки
uv run pre-commit install
```

## Запуск локально

Каждый сервис — отдельный uvicorn-процесс:

```bash
uv run uvicorn main:app --app-dir b2b/src        --reload --port 8001
uv run uvicorn main:app --app-dir b2c/src        --reload --port 8002
uv run uvicorn main:app --app-dir moderation/src --reload --port 8003
```

Swagger UI у каждого — `/docs`, OpenAPI JSON — `/openapi.json`.

## Запуск в Docker

```bash
docker compose up --build
```

| Сервис     | URL                   |
|------------|-----------------------|
| b2b        | http://localhost:8001 |
| b2c        | http://localhost:8002 |
| moderation | http://localhost:8003 |

**Как устроены образы:** каждый Dockerfile тянет только свои файлы (`<service>/pyproject.toml` + `<service>/src` + `shared/` + корневой `uv.lock`), делает `uv sync --frozen --package <name> --no-dev` в `/app/.venv`, запускает `uvicorn` напрямую. Манифесты других сервисов в образ не попадают.

## Тесты, линтер, типы

```bash
uv run pytest                         # все тесты (b2b/tests, b2c/tests, moderation/tests, shared/tests)
uv run ruff check .                   # линт
uv run ruff format .                  # форматирование
uv run mypy shared/src b2b/src b2c/src moderation/src  # типы
```

## Добавить зависимость

В конкретный сервис:
```bash
uv add --package b2c-service <package>
```

В общую библиотеку `shared`:
```bash
uv add --package shared <package>
```

В dev-группу workspace:
```bash
uv add --group dev <package>
```

После любого `uv add` коммитьте обновлённый `uv.lock`.
