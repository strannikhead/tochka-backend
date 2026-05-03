# NeoMarket Backend

> Монорепозиторий бэкенда учебного маркетплейса NeoMarket — три независимых микросервиса, общая библиотека, единый `uv.lock` на весь workspace.

[![Python](https://img.shields.io/badge/Python-3.14-3776ab?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![uv](https://img.shields.io/badge/uv-workspace-de5fe9?logo=astral)](https://docs.astral.sh/uv/)
[![API Docs](https://img.shields.io/badge/API%20Docs-Swagger%20UI-85ea2d?logo=swagger)](https://urfu2026-neomarket.github.io/neomarket-protocols/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

---

## Команда и курс

### Ключевые ссылки

| Ресурс | Ссылка |
|--------|--------|
| Этот репо (бэкенд) | https://github.com/strannikhead/tochka-backend |
| Общий протокольный репо | https://github.com/URFU2026-NeoMarket/neomarket-protocols |
| Форк протоколов для PR | https://github.com/trueforme/tochka-neomarket |
| Swagger UI (актуальный master) | https://urfu2026-neomarket.github.io/neomarket-protocols/ |
| Гайд по курсу | https://github.com/tochka-public/NeoMarket---Student-Guide |
| Сайт БРС и квестов | https://contract.tochka-urfu.tech |
| Шаблон PR | https://github.com/URFU2026-NeoMarket/neomarket-protocols/blob/master/.github/pull_request_template.md |
| Процесс ревью | https://github.com/URFU2026-NeoMarket/neomarket-protocols/blob/master/.github/REVIEW_PROCESS.md |

### БРС

- **60 баллов** — выполнить все три сервиса с тестами и рабочими ручками (обязательные квесты на сайте)
- **80+ баллов** — нужны доп. активности: PR в протоколы, активности на парах, доп. задания

### Как работать с API и квестами

**Перед задачей — сверить OpenAPI:**  
Открыть [Swagger UI](https://urfu2026-neomarket.github.io/neomarket-protocols/) (master) и убедиться, что нужный эндпоинт уже есть.

**Если эндпоинта нет в апстриме:**  
Форкнуть [neomarket-protocols](https://github.com/URFU2026-NeoMarket/neomarket-protocols) → добавить/изменить `openapi.yaml` → открыть PR. Кто первый — получает бонусные баллы (speedrun-бонус: +50% / +30% / +10% Rep первым трём командам).

**Если эндпоинт есть:**  
Идти на сайт [contract.tochka-urfu.tech](https://contract.tochka-urfu.tech), выбрать задачу, реализовать в коде.

**Как сдавать квест:**  
Открыть feature-ветку → реализовать → открыть PR в `main` этого репо.  
В описании PR обязательно указать **ADR**: какие альтернативы рассматривал, какую выбрал и почему.

---

## Архитектура

```
┌─────────────────────────────────────────────────────────┐
│                     NeoMarket Backend                    │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │     B2B      │  │     B2C      │  │  Moderation  │  │
│  │  :8001       │◄─┤  :8002       │  │  :8003       │  │
│  │  Seller Cab. │  │  Buyer App   │  │  Card Review │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                 │                  │          │
│         └─────────────────┴──────────────────┘          │
│                           │                             │
│              ┌────────────▼────────────┐                │
│              │         shared/         │                │
│              │  Pydantic models, JWT,  │                │
│              │  HTTP-clients           │                │
│              └─────────────────────────┘                │
└─────────────────────────────────────────────────────────┘
```

B2C обращается к B2B за актуальными ценами и остатками через async HTTP (httpx).  
Каждый сервис имеет свою PostgreSQL-базу и деплоится независимо.

---

## Сервисы

### B2B — Seller Cabinet (`localhost:8001`)

Личный кабинет продавца: управление товарами, SKU и накладными.

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/api/v1/products` | Создать товар |
| `GET` | `/api/v1/products/{id}` | Получить товар |
| `PUT` | `/api/v1/products/{id}` | Обновить товар |
| `POST` | `/api/v1/skus` | Создать SKU |
| `PUT` | `/api/v1/skus` | Обновить SKU |
| `POST` | `/api/v1/invoices` | Создать накладную |
| `POST` | `/api/v1/invoices/accept` | Принять накладную |

### B2C — Buyer App (`localhost:8002`)

Покупательский интерфейс: каталог, корзина, избранное, главная страница.

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/api/v1/products` | Список товаров |
| `GET` | `/api/v1/products/{id}` | Карточка товара |
| `GET` | `/api/v1/products/{id}/similar` | Похожие товары |
| `GET` | `/api/v1/products/{id}/skus` | SKU товара |
| `GET` | `/api/v1/products/{id}/skus/{sku_id}` | Конкретный SKU |
| `GET` | `/api/v1/categories` | Список категорий |
| `GET` | `/api/v1/categories/{id}` | Категория |
| `GET` | `/api/v1/categories/{id}/filters` | Фильтры категории |
| `GET` | `/api/v1/catalog/facets` | Фасеты каталога |
| `GET` | `/api/v1/breadcrumbs` | Хлебные крошки |
| `GET` | `/api/v1/cart` | Корзина |
| `DELETE` | `/api/v1/cart` | Очистить корзину |
| `POST` | `/api/v1/cart/items` | Добавить в корзину |
| `GET` | `/api/v1/cart/items/{item_id}` | Позиция корзины |
| `PUT` | `/api/v1/cart/items/{item_id}` | Изменить количество |
| `DELETE` | `/api/v1/cart/items/{item_id}` | Удалить из корзины |
| `GET` | `/api/v1/cart/also_bought` | «Вместе покупают» |
| `GET` | `/api/v1/favorites` | Список избранного |
| `POST` | `/api/v1/favorites/{product_id}` | Добавить в избранное |
| `DELETE` | `/api/v1/favorites/{product_id}` | Убрать из избранного |
| `POST` | `/api/v1/favorites/{product_id}/subscribe` | Подписка на наличие |
| `GET` | `/api/v1/home/banners` | Баннеры главной |
| `GET` | `/api/v1/main/collections` | Подборки |
| `GET` | `/api/v1/collections/{id}/products` | Товары подборки |
| `POST` | `/api/v1/banner-events` | Событие баннера |

### Moderation (`localhost:8003`)

Модерация карточек товаров перед публикацией.

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/api/v1/product-moderation/get-next` | Получить следующую карточку |
| `POST` | `/api/v1/products/{id}/approve` | Одобрить товар |
| `POST` | `/api/v1/products/{id}/decline` | Отклонить товар |
| `GET` | `/api/v1/product-blocking-reasons` | Причины блокировки |

---

## Стек

| Категория | Технологии |
|-----------|-----------|
| **Runtime** | Python 3.14, [uv](https://docs.astral.sh/uv/) workspace |
| **Framework** | FastAPI + Uvicorn (ASGI) |
| **Validation** | Pydantic v2 + pydantic-settings |
| **ORM / DB** | SQLAlchemy (asyncio) + Alembic + PostgreSQL 18 (psycopg v3) |
| **Auth** | PyJWT (`Authorization: Bearer`) |
| **Cache** | Redis |
| **HTTP Client** | httpx (async, inter-service) |
| **Linting** | Ruff (lint + format) |
| **Types** | mypy |
| **Tests** | pytest + schemathesis (contract testing по OpenAPI) |
| **Git hooks** | pre-commit |
| **Deploy** | Docker + Docker Compose |

---

## Быстрый старт

### Локально

```bash
# uv сам установит Python 3.14, если нужно
uv sync --all-packages

# установить git-хуки
uv run pre-commit install
```

Запустить каждый сервис отдельно:

```bash
uv run uvicorn main:app --app-dir b2b/src        --reload --port 8001
uv run uvicorn main:app --app-dir b2c/src        --reload --port 8002
uv run uvicorn main:app --app-dir moderation/src --reload --port 8003
```

Swagger UI — `/docs`, OpenAPI JSON — `/openapi.json`.

### Docker Compose

```bash
docker compose up --build
```

| Сервис | URL | База данных |
|--------|-----|-------------|
| B2B | http://localhost:8001 | `neomarket_b2b` |
| B2C | http://localhost:8002 | `neomarket_b2c` |
| Moderation | http://localhost:8003 | `neomarket_moderation` |

---

## Разработка

### Тесты, линтер, типы

```bash
# тесты всех сервисов
uv run pytest

# линт
uv run ruff check .

# форматирование
uv run ruff format .

# статическая типизация
uv run mypy shared/src b2b/src b2c/src moderation/src
```

### Добавить зависимость

```bash
# в конкретный сервис
uv add --package b2c-service <package>

# в общую библиотеку
uv add --package shared <package>

# в dev-группу workspace
uv add --group dev <package>
```

После `uv add` — коммитьте обновлённый `uv.lock`.

---

## Структура репозитория

```
.
├── b2b/                     # Seller Cabinet (B2B)
│   ├── src/api/{products,skus,invoices}/
│   ├── tests/
│   ├── alembic/             # DB-миграции
│   ├── openapi.yaml
│   └── Dockerfile
├── b2c/                     # Buyer App (B2C)
│   ├── src/api/{catalog,products,categories,cart,favorites,home}/
│   ├── tests/
│   ├── alembic/
│   ├── {catalog,cart,orders}/openapi.yaml
│   └── Dockerfile
├── moderation/              # Card Moderation
│   ├── src/api/{product_moderation,blocking_reasons}/
│   ├── tests/
│   ├── alembic/
│   ├── openapi.yaml
│   └── Dockerfile
├── shared/                  # Общая библиотека
│   └── src/shared/          # Pydantic-модели, JWT, HTTP-клиенты
├── docker-compose.yml
├── pyproject.toml           # uv workspace root + dev-tools
└── uv.lock
```
