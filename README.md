# NeoMarket Protocols

[![API Docs](https://img.shields.io/badge/API%20Docs-Swagger%20UI-85ea2d?logo=swagger)](https://urfu2026-neomarket.github.io/neomarket-protocols/)

OpenAPI-спецификации модулей NeoMarket. Восстановлены на Protocol Summit.

## Структура

| Директория | Модуль | Кто проектирует |
|-----------|--------|-----------------|
| `b2b/` | Seller Cabinet (B2B) | reference |
| `moderation/` | Moderation | reference |
| `b2c/catalog/` | Каталог + Карточка товара | Forge |
| `b2c/cart/` | Корзина + Избранное + Главная | Interface |
| `b2c/orders/` | Заказы | QA Corps |
| `shared/` | Общие схемы (Product, SKU, etc.) | все |

## Как работать

### Два способа внести изменения

**Способ 1 — Contributor (без форка)**

Напишите координатору вашего синдиката в Telegram — он добавит вас в team `contributors`. После этого вы можете пушить ветки напрямую в этот репозиторий.

**Способ 2 — Fork**

Если не хотите ждать — сделайте fork и отправьте PR из него.

### Флоу работы

1. **Создать ветку** от `master`:

```bash
git checkout -b {syndicate}/{team}/{block}
```

Примеры:
- `forge/copypaste/text-search`
- `interface/hackerman/cart-add`
- `qa-corps/bug-hunters/checkout`

2. **Написать спеку** — добавьте или отредактируйте `openapi.yaml` в директории вашего домена.

3. **Запушить и создать PR**:

```bash
git push origin {ваша-ветка}
```

Создайте Pull Request на GitHub. При создании PR автоматически запустится валидация OpenAPI. Координатор вашего синдиката проверит и смержит.

## Как смотреть документацию

### Онлайн (GitHub Pages)

Документация доступна по адресу: https://urfu2026-neomarket.github.io/neomarket-protocols/

Swagger UI с dropdown для переключения между модулями: B2B, B2C Каталог, B2C Корзина, B2C Заказы, Moderation.

### Локально

```bash
npm install
npm run docs
```

Откроется `http://localhost:3000` с тем же Swagger UI.

Если зависимости уже установлены и спеки уже собраны, можно запустить только сервер:

```bash
npm run docs:serve
```

## Координаторы

| Синдикат | Координатор |
|----------|-------------|
| Forge | @Ulyanayou |
| Interface | @shchavr |
| QA Corps | @TimofeyChugunov |

## Домены B2C (блоки для claim)

### Forge — Каталог + Карточка товара
1. Текстовый поиск
2. Фильтры по характеристикам
3. Пагинация + сортировка
4. Карточка: основная инфо + фото
5. Карточка: выбор SKU (цена, наличие)
6. Связанные товары / рекомендации
7. Эндпоинты B2C -> B2B: формат запроса данных

### Interface — Корзина + Избранное + Главная
1. Корзина: добавить товар
2. Корзина: просмотр (актуальные цены из B2B)
3. Корзина: изменить количество / удалить
4. Избранное: CRUD + список
5. Главная: категории + баннеры
6. Главная: подборки / популярные
7. Обогащение данных: как получать цены/остатки из B2B

### QA Corps — Заказы
1. Checkout: из корзины -> резерв -> заказ
2. Статусы заказа: state machine
3. Отмена заказа + unreserve
4. История заказов: список + детали
5. Резервирование: формат B2C -> B2B
6. Edge cases: товар заблокирован / закончился
