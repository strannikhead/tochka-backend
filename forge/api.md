## Endpoint

**GET** `/api/v1/products/{id}`

Возвращает **базовую информацию товара для карточки**: заголовок, описание, категорию и изображения.

### Path parameters

* `id` — идентификатор товара (uuid)

### Query parameters

Нет.

### Request body

Нет.

---

# Успешный ответ

### 200 OK

```json
{
  "id": 42,
  "title": "iPhone 15 Pro Max",
  "description": "Флагман Apple...",
  "status": "MODERATED",
  "category": {
    "id": 3,
    "name": "Смартфоны"
  },
  "images": [
    {
      "url": "https://cdn.example.com/products/42/iphone15-1.jpg",
      "ordering": 0
    },
    {
      "url": "https://cdn.example.com/products/42/iphone15-2.jpg",
      "ordering": 1
    }
  ]
}
```

### Поля ответа

| Поле              | Тип        | Описание                        |
| ----------------- | ---------- | ------------------------------- |
| id                | uuid       | идентификатор товара            |
| title             | string     | заголовок товара                |
| description       | string     | описание товара                 |
| status            | string     | статус модерации товара         |
| category          | object     | категория товара                |
| category.id       | int        | идентификатор категории         |
| category.name     | string     | название категории              |
| images            | object[]   | список изображений товара       |
| images[].url      | string     | URL изображения                 |
| images[].ordering | int        | порядок отображения изображения |

---

# Ошибки

### 400 Bad Request

Некорректный формат `id`.

```json
{
  "error": {
    "code": "INVALID_PRODUCT_ID",
    "message": "Invalid product id"
  }
}
```

---

### 404 Not Found

Товар не существует **или недоступен**.

```json
{
  "error": {
    "code": "PRODUCT_NOT_FOUND",
    "message": "Product not found"
  }
}
```

---

### 429 Too Many Requests

Превышен лимит запросов.

---

### 500 Internal Server Error

Внутренняя ошибка сервиса.

---

## Важные договоренности

**Изображения**

* возвращаются **готовые CDN URL**
* список отсортирован по `ordering`
* изображение с `ordering = 0` используется как **основное фото**
* массив `images` может быть пустым

**Статус товара**

`status` отражает состояние товара в системе модерации, например:

* `DRAFT`
* `PENDING_MODERATION`
* `MODERATED`
* `REJECTED`

Поведение API для недоступных товаров определяется бизнес-логикой (например, возврат `404`).
