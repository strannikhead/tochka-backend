## Endpoint

**GET** `/api/v1/products/{id}`

Возвращает **базовую информацию товара для карточки**: заголовок, описание и фотографии.

### Path parameters

* `id` — идентификатор товара (int / uuid — зависит от вашей модели)

### Query parameters

Нет.

### Request body

Нет.

---

# Успешный ответ

### 200 OK

```json
{
  "id": "123",
  "title": "Кроссовки Nike Air",
  "description": "Описание товара...",
  "photos": [
    "https://cdn.example.com/products/123/1.jpg",
    "https://cdn.example.com/products/123/2.jpg",
    "https://cdn.example.com/products/123/3.jpg"
  ]
}
```

### Поля ответа

| Поле        | Тип          | Описание                                        |
| ----------- | ------------ | ----------------------------------------------- |
| id          | uuid / int | идентификатор товара                            |
| title       | string       | заголовок товара                                |
| description | string       | описание товара                                 |
| photos      | string[]     | массив URL изображений (первое — основное фото) |

Дополнительно:

* `photos` может быть пустым массивом `[]`
* порядок фото **фиксированный**

---

# Ошибки

### 400 Bad Request

Некорректный формат id.

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

 **Фото**
   * возвращаются **уже CDN URL**
   * порядок соответствует `sort_order`
   * первое фото используется как главное

