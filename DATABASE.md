# База данных и миграции

## Структура

Проект использует PostgreSQL 18 с тремя отдельными базами данных:
- `neomarket_b2b` — для B2B сервиса (товары, категории, SKU)
- `neomarket_b2c` — для B2C сервиса (пользователи, корзина, заказы, избранное)
- `neomarket_moderation` — для Moderation сервиса (модерация товаров)

## Схема базы данных

### B2B сервис

**categories**
- `id` (UUID) — уникальный идентификатор
- `name` (String) — название категории
- `parent_id` (UUID) — родительская категория
- `level` (Integer) — уровень вложенности
- `path` (Text) — путь категории (иерархия через точку)
- `is_active` (Boolean) — активна ли категория
- `created_at`, `updated_at` (DateTime)

**products**
- `id` (UUID) — уникальный идентификатор
- `title` (String) — название товара
- `description` (Text) — описание
- `status` (Enum) — статус: CREATED, ON_MODERATION, MODERATED, BLOCKED, DELETED
- `category_id` (UUID) — категория товара
- `images` (JSONB) — массив изображений
- `characteristics` (JSONB) — характеристики товара
- `created_at`, `updated_at` (DateTime)

**skus**
- `id` (UUID) — уникальный идентификатор
- `product_id` (UUID) — товар
- `name` (String) — название варианта (например, "256GB Black")
- `price` (Integer) — цена в копейках
- `active_quantity` (Integer) — количество на складе
- `images` (JSONB) — изображения SKU
- `characteristics` (JSONB) — характеристики SKU
- `created_at`, `updated_at` (DateTime)

### B2C сервис

**users**
- `id` (UUID), `email`, `phone`, `password_hash`
- `first_name`, `last_name`, `is_active`
- `created_at`, `updated_at`

**favorites**
- `id` (UUID), `user_id` (UUID), `product_id` (UUID)
- `added_at` (DateTime)

**cart_items**
- `id` (UUID), `user_id` (UUID), `sku_id` (UUID)
- `quantity` (Integer)
- `added_at`, `updated_at`

**addresses**
- `id` (UUID), `user_id` (UUID)
- `city`, `street`, `house`, `apartment`, `postal_code`
- `is_default` (Boolean)
- `created_at`, `updated_at`

**orders**
- `id` (UUID), `user_id` (UUID), `address_id` (UUID)
- `status` (Enum) — PENDING, CONFIRMED, PROCESSING, SHIPPED, DELIVERED, CANCELLED
- `total_price` (Integer), `delivery_notes` (Text)
- `created_at`, `updated_at`

**order_items**
- `id` (UUID), `order_id` (UUID), `sku_id` (UUID)
- `quantity` (Integer), `price` (Integer)
- `created_at`

**banners**
- `id` (UUID), `title`, `image_url`, `link`
- `ordering` (Integer), `is_active` (Boolean)
- `created_at`, `updated_at`

**collections**
- `id` (UUID), `title`, `description`
- `product_ids` (JSONB) — массив ID товаров
- `ordering` (Integer), `is_active` (Boolean)
- `created_at`, `updated_at`

### Moderation сервис

**product_snapshots**
- `id` (UUID), `product_id` (UUID)
- `snapshot_data` (JSONB) — снимок данных товара
- `is_moderated` (Boolean)
- `created_at`

**blocking_reasons**
- `id` (UUID), `code`, `description`
- `is_active` (Boolean)
- `created_at`

**moderation_decisions**
- `id` (UUID), `snapshot_id` (UUID), `reason_id` (UUID)
- `decision` (Enum) — APPROVED, DECLINED
- `moderator_id` (UUID), `comment` (Text)
- `created_at`

## Запуск с docker-compose

### Вариант 1: Только база данных

```bash
docker compose -f docker-compose.db.yml up -d
```

Доступ к БД:
- **Host:** localhost
- **Port:** 5432
- **User:** neomarket
- **Password:** neomarket_dev_2026
- **Databases:** neomarket_b2b, neomarket_b2c, neomarket_moderation

### Вариант 2: Все сервисы + БД

```bash
docker compose up --build
```

Это запустит:
- PostgreSQL на порту 5432
- B2B сервис на порту 8001
- B2C сервис на порту 8002
- Moderation сервис на порту 8003

**Важно:** Миграции применяются автоматически при запуске каждого сервиса!

## Локальная разработка

### Применение миграций вручную

Для каждого сервиса:

```bash
# B2B
cd b2b
DATABASE_URL="postgresql+psycopg://neomarket:neomarket_dev_2026@localhost:5432/neomarket_b2b" \
  alembic upgrade head

# B2C
cd b2c
DATABASE_URL="postgresql+psycopg://neomarket:neomarket_dev_2026@localhost:5432/neomarket_b2c" \
  alembic upgrade head

# Moderation
cd moderation
DATABASE_URL="postgresql+psycopg://neomarket:neomarket_dev_2026@localhost:5432/neomarket_moderation" \
  alembic upgrade head
```

### Создание новой миграции

```bash
# B2B
cd b2b
DATABASE_URL="postgresql+psycopg://neomarket:neomarket_dev_2026@localhost:5432/neomarket_b2b" \
  alembic revision --autogenerate -m "описание изменений"

# B2C
cd b2c
DATABASE_URL="postgresql+psycopg://neomarket:neomarket_dev_2026@localhost:5432/neomarket_b2c" \
  alembic revision --autogenerate -m "описание изменений"

# Moderation
cd moderation
DATABASE_URL="postgresql+psycopg://neomarket:neomarket_dev_2026@localhost:5432/neomarket_moderation" \
  alembic revision --autogenerate -m "описание изменений"
```

### Откат миграций

```bash
# Откатить последнюю миграцию
alembic downgrade -1

# Откатить все миграции
alembic downgrade base
```

## Переменные окружения

Каждый сервис использует переменную `DATABASE_URL` для подключения к БД:

- **B2B:** `postgresql+psycopg://neomarket:neomarket_dev_2026@localhost:5432/neomarket_b2b`
- **B2C:** `postgresql+psycopg://neomarket:neomarket_dev_2026@localhost:5432/neomarket_b2c`
- **Moderation:** `postgresql+psycopg://neomarket:neomarket_dev_2026@localhost:5432/neomarket_moderation`

В Docker-контейнерах hostname `localhost` заменяется на `postgres` (имя сервиса).

## Автоматическое применение миграций

При запуске через Docker Compose каждый сервис:
1. Ждет готовности PostgreSQL (healthcheck)
2. Автоматически применяет все миграции (`alembic upgrade head`)
3. Запускает приложение

Это реализовано через entrypoint скрипты в каждом Dockerfile.

## Работа с psql

```bash
# Подключиться к контейнеру
docker exec -it neomarket-postgres psql -U neomarket

# Подключиться к конкретной БД
docker exec -it neomarket-postgres psql -U neomarket -d neomarket_b2b

# Или напрямую с хоста (если установлен psql)
psql -h localhost -U neomarket -d neomarket_b2b
```

## Сброс БД

```bash
# Остановить и удалить контейнеры + volumes
docker compose down -v

# Запустить заново (БД будет пересоздана)
docker compose up --build
```
