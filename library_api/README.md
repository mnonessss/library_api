# Library Service

Backend-сервис системы управления библиотекой на FastAPI и PostgreSQL. Проект подготовлен для модуля по масштабированию баз данных: оптимизация запросов, индексы, партиционирование, репликация и шардирование.

## О проекте

Сервис позволяет управлять пользователями, книгами, категориями, бронированиями книг и отзывами. Пользователи могут бронировать книги, оставлять отзывы с оценкой. Книги связаны с категориями через связь many-to-many.

## Запуск

```bash
docker compose up -d --build
```

После запуска доступны:
- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- Health check: http://localhost:8000/health


Компоненты Docker Compose:
- **backend** — FastAPI-приложение (порт 8000)
- **db** — PostgreSQL 15 (порт 5460 на хосте)


| Таблица | Описание |
|---------|----------|
| `users` | Читатели библиотеки |
| `books` | Книги |
| `categories` | Жанры / категории |
| `book_categories` | Связь M:N между книгами и категориями |
| `bookings` | Бронирования книг |
| `reviews` | Отзывы пользователей о книгах |

## Основные endpoint'ы

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Проверка работоспособности и подключения к БД |
| GET/POST/PUT/DELETE | `/api/users` | CRUD пользователей |
| GET | `/api/users/{id}/bookings` | Бронирования пользователя (JOIN) |
| GET | `/api/users/{id}/reviews` | Отзывы пользователя (JOIN) |
| GET/POST/PUT/DELETE | `/api/books` | CRUD книг |
| GET | `/api/books?search=...` | Поиск книг с категориями (JOIN) |
| GET | `/api/books/popular` | Топ популярных книг (агрегация) |
| GET | `/api/books/{id}/bookings` | Бронирования книги (JOIN) |
| GET | `/api/books/{id}/reviews` | Отзывы на книгу (JOIN) |
| GET/POST/PUT/DELETE | `/api/bookings` | CRUD бронирований |
| GET | `/api/bookings?page=1&page_size=20&status=ACTIVE&from_date=...&sort=-created_at` | Пагинация, фильтрация, сортировка |
| GET/POST/PUT/DELETE | `/api/reviews` | CRUD отзывов |
| GET | `/api/reviews/stats/ratings` | Средний рейтинг книг (агрегация) |

## Основная сущность для масштабирования

**Таблица:** `bookings`

**Почему она подходит:** Бронирования создаются при каждом обращении читателя к библиотеке. Объём записей растёт линейно с числом пользователей и активностью. У таблицы есть `created_at`, что удобно для партиционирования по времени и последующих экспериментов с производительностью.

## Индексы таблицы `bookings`

| Индекс | Колонки | Зачем нужен |
|--------|---------|-------------|
| `bookings_partitioned_pkey` | `(id, created_at)` | PK партиционированной таблицы (ключ обязан включать `created_at`) |
| `ix_bookings_id` | `id` | Поиск бронирования по id (без pruning, обход партиций) |
| `ix_bookings_user_id` | `user_id` | История бронирований читателя |
| `ix_bookings_book_id` | `book_id` | Кто бронировал конкретную книгу |
| `ix_bookings_status` | `status` | Фильтрация по статусу (низкая селективность) |
| `ix_bookings_created_at` | `created_at` | Диапазоны дат и сортировка |
| `idx_bookings_status_created_at` | `(status, created_at)` | Список бронирований с фильтром по статусу и дате |
| `idx_bookings_user_created` | `(user_id, created_at DESC)` | История читателя с сортировкой |

`bookings` партиционирована по `RANGE (created_at)` помесячно (миграция `d4e5f6a7b8c9`). Запросы с фильтром по дате используют partition pruning.

Составной индекс `idx_bookings_status_created_at` добавлен миграцией `c3d4e5f6a7b8` и используется запросом `GET /api/bookings?status=...&from_date=...`.

## Партиции и алерты

Ночные job'ы крутит **pg_cron** на Primary (`0 1 * * *` создание, `5 1 * * *` health):

```sql
SELECT jobid, jobname, schedule, command FROM cron.job;
SELECT maintain_partitions();
SELECT * FROM check_partition_health();
SELECT * FROM partition_alert_log ORDER BY created_at DESC;
```

Ручной вызов из backend (та же SQL-функция): `POST /admin/partitions/create`, `POST /admin/partitions/health`. Демо сбоя: `POST /admin/partitions/demo/break` и `/demo/restore`.

Алерты от pg_cron пишутся в `partition_alert_log`. Повтор CRITICAL не отправляется. Переход CRITICAL → OK даёт recovery.

## Сложные запросы

### JOIN №1 — бронирования пользователя с названием книги

```sql
SELECT bookings.*, books.title AS book_title
FROM bookings
JOIN books ON bookings.book_id = books.id
WHERE bookings.user_id = :user_id
ORDER BY bookings.created_at DESC;
```

Используется в: `GET /api/users/{id}/bookings`

### JOIN №2 — поиск книг с категориями

```sql
SELECT DISTINCT books.*, categories.name AS category_name
FROM books
LEFT JOIN book_categories ON books.id = book_categories.book_id
LEFT JOIN categories ON book_categories.category_id = categories.id
WHERE books.title ILIKE :search
ORDER BY books.created_at DESC;
```

Используется в: `GET /api/books?search=...`

### Агрегирующий запрос — топ популярных книг

```sql
SELECT books.id, books.title, books.author, COUNT(bookings.id) AS booking_count
FROM bookings
JOIN books ON bookings.book_id = books.id
GROUP BY books.id, books.title, books.author
ORDER BY booking_count DESC
LIMIT :limit;
```

Используется в: `GET /api/books/popular`

### Агрегирующий запрос — средний рейтинг книг

```sql
SELECT books.id, books.title,
       COUNT(reviews.id) AS review_count,
       ROUND(AVG(reviews.rating)::numeric, 2) AS average_rating
FROM reviews
JOIN books ON reviews.book_id = books.id
GROUP BY books.id, books.title
ORDER BY average_rating DESC;
```

Используется в: `GET /api/reviews/stats/ratings`

## Генерация данных

Скрипт для массовой генерации тестовых данных:

```bash
# Полная генерация (только если база пустая)
docker compose exec backend python scripts/generate_data.py

# Добавить только отзывы к уже существующим данным
docker compose exec backend python scripts/generate_data.py --only-reviews

# Полная перегенерация с очисткой всех таблиц
docker compose exec backend python scripts/generate_data.py --reset
```

По умолчанию создаёт:
- 10 категорий
- 1 000 пользователей
- 500 книг
- 100 000 бронирований
- 50 000 отзывов

Масштаб можно изменить через аргументы:

```bash
docker compose exec backend python scripts/generate_data.py --reset \
  --users 10000 --books 5000 --bookings 1000000 --reviews 500000
```
