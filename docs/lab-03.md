# Лабораторная 3. Партиционирование PostgreSQL


# Часть 1. RANGE PARTITIONING по дате

```sql
CREATE TABLE events (
    id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    payload TEXT,
    created_at TIMESTAMP NOT NULL
) PARTITION BY RANGE (created_at);

CREATE TABLE events_2026_09_09 PARTITION OF events
    FOR VALUES FROM ('2026-09-09') TO ('2026-09-10');
CREATE TABLE events_2026_09_10 PARTITION OF events
    FOR VALUES FROM ('2026-09-10') TO ('2026-09-11');
CREATE TABLE events_2026_09_11 PARTITION OF events
    FOR VALUES FROM ('2026-09-11') TO ('2026-09-12');
```

Загружено 30 000 случайных событий за три дня плюс контрольные строки. Распределение:

| Партиция | Строк |
| :--- | ---: |
| `events_2026_09_09` | 10 164 |
| `events_2026_09_10` | 9 903 |
| `events_2026_09_11` | 9 935 |

Контрольные вставки:

| `created_at` | Куда попала |
| :--- | :--- |
| `2026-09-10 12:00:00` | `events_2026_09_10` |
| `2026-09-11 00:00:00` | `events_2026_09_11` |

Вставка за 12 сентября:

```
ERROR:  no partition of relation "events" found for row
DETAIL:  Partition key of the failing row contains (created_at) = (2026-09-12 00:00:00).
```

### Ответы

1. **`created_at = '2026-09-10 12:00:00'`** попадает в `events_2026_09_10`. Диапазон `[2026-09-10, 2026-09-11)`.
2. **`created_at = '2026-09-11 00:00:00'`** попадает в `events_2026_09_11`. Полночь 11-го — это уже следующая партиция, а не конец десятого.
3. **Запись за 2026-09-12.** `INSERT` падает: подходящей партиции нет. Приложение увидит ошибку, данные не запишутся.
4. **Почему `TO ('2026-09-11')` не включает эту дату?**  
   В PostgreSQL RANGE — полуинтервал `[FROM, TO)`: нижняя граница входит, верхняя нет. Иначе полночь принадлежала бы двум партициям сразу. Поэтому 11 сентября 00:00 — это начало `events_2026_09_11`.

---

# Часть 2. Partition pruning

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM events
WHERE created_at >= '2026-09-10'
  AND created_at < '2026-09-11';
```

```
Aggregate  (actual time=1.077..1.077 rows=1)
  ->  Seq Scan on events_2026_09_10 events
        Filter: ((created_at >= ...) AND (created_at < ...))
        Buffers: shared hit=79
Execution Time: 1.095 ms
```

- PostgreSQL проверил **одну** партицию: `events_2026_09_10`.
- Именно она нужна: условие совпадает с её диапазоном.
- Остальные две **исключены**: в плане нет `Append` и нет сканов `events_2026_09_09` / `events_2026_09_11`.
- Pruning виден по тому, что узел сканирования сразу указывает на дочернюю таблицу, а не на родителя со списком всех детей.

Запрос без ключа партиционирования:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*) FROM events WHERE event_type = 'click';
```

```
Aggregate  (actual time=3.203..3.204)
  ->  Append
        ->  Seq Scan on events_2026_09_09  Filter: event_type = 'click'
        ->  Seq Scan on events_2026_09_10
        ->  Seq Scan on events_2026_09_11
Execution Time: 3.224 ms
```

### Вопрос. Почему второй запрос может обращаться ко всем партициям?

`event_type` не входит в ключ `RANGE (created_at)`. Планировщик не знает, в какой дневной партиции лежат `click`, и обязан открыть все. Pruning работает только когда в `WHERE` (или JOIN) есть ограничение по partition key, из которого следует, что часть диапазонов пуста.

---

# Часть 3. RANGE по числу

```sql
CREATE TABLE products (
    id BIGINT NOT NULL,
    name TEXT NOT NULL,
    price NUMERIC NOT NULL
) PARTITION BY RANGE (price);
```

| Партиция | Диапазон | Товары |
| :--- | :--- | :--- |
| `products_cheap` | `[0, 100)` | Pencil 15, Notebook 80 |
| `products_medium` | `[100, 1000)` | Keyboard 250, Monitor 799 |
| `products_expensive` | `[1000, MAXVALUE)` | Workstation 2500, Server 4800 |

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM products WHERE price >= 100 AND price < 500;
```

```
Seq Scan on products_medium products
  Filter: ((price >= 100) AND (price < 500))
  Rows Removed by Filter: 1
Execution Time: 0.006 ms
```

PostgreSQL должен просмотреть **только `products_medium`**. Условие `[100, 500)` целиком лежит внутри `[100, 1000)`. `cheap` заканчивается на 100 (не включая), `expensive` начинается с 1000. Monitor (799) в партиции есть, но отфильтровывается уже внутри неё.

---

# Часть 4. LIST PARTITIONING

```sql
CREATE TABLE customers (...) PARTITION BY LIST (customer_type);
-- FOR VALUES IN ('B2C') / ('B2B') / ('Enterprise')
```

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM customers WHERE customer_type = 'B2B';
```

```
Seq Scan on customers_b2b customers
  Filter: ((customer_type)::text = 'B2B'::text)
Execution Time: 0.009 ms
```

- Используется **`customers_b2b`**.
- Остальные не читаются: значение `'B2B'` однозначно задаёт одну партицию списка.
- **Отличие от RANGE:** RANGE режет непрерывную ось (даты, цены). LIST режет дискретное множество меток. Pruning для LIST — это точное совпадение значения, а не пересечение интервалов.

---

# Часть 5. Неизвестное значение и DEFAULT

```sql
INSERT INTO customers VALUES (100, 'Test User', 'VIP');
-- ERROR: no partition of relation "customers" found for row
-- DETAIL: Partition key ... (customer_type) = (VIP).
```

После `CREATE TABLE customers_default PARTITION OF customers DEFAULT;` та же вставка проходит: строка оказывается в `customers_default`.

### Ответы

1. **Зачем DEFAULT.** Чтобы значения, для которых ещё нет партиции, не роняли `INSERT`.
2. **Чем полезна.** Можно завести новый тип клиента и не останавливать запись, пока не создадут отдельную партицию.
3. **Какие проблемы.** DEFAULT превращается в свалку. Pruning по `customer_type = 'VIP'` пойдёт в default (и только туда, если значение не перечислено). Но `SELECT * WHERE customer_type = 'B2B'` default не читает. Если в default скопятся разные типы, запросы по «новым» типам сканируют всё default целиком. Потом вынести значение из default в новую LIST-партицию сложнее: нужно `DETACH`, переложить строки, создать `FOR VALUES IN ('VIP')`. Для временных рядов DEFAULT ещё опаснее: он пересекается с будущими RANGE и мешает добавить партицию на новый день.

---

# Часть 6. HASH PARTITIONING

```sql
CREATE TABLE user_events (...) PARTITION BY HASH (user_id);
-- 4 партиции: MODULUS 4, REMAINDER 0..3
```

200 000 строк:

| Партиция | Строк | Доля |
| :--- | ---: | ---: |
| `user_events_0` | 50 028 | 25.01% |
| `user_events_1` | 50 180 | 25.09% |
| `user_events_2` | 49 883 | 24.94% |
| `user_events_3` | 49 909 | 24.95% |

### Ответы

1. **Насколько равномерно?** Почти идеально: разброс около ±0.1 п.п. HASH как раз для этого и нужен.
2. **Почему полезен?** Равномерная нагрузка на диски/шарды, нет «горячего» месяца. Подходит, когда нет естественного диапазона, а ключ высококардинальный (`user_id`).
3. **Чем отличается от RANGE?** RANGE группирует близкие значения ключа вместе. HASH раскидывает соседние `user_id` по разным корзинам. Pruning у HASH есть только при равенстве (или `IN`) по `user_id`, не по диапазону дат.
4. **Почему плохо «удалить старше 3 лет»?** Строки за 2020 и 2026 с одним `user_id` лежат в одной партиции. `DROP PARTITION` удалит и свежие данные. Для TTL по времени нужен RANGE по `created_at`.

---

# Часть 7. Выбор стратегии

**Сценарий A — миллионы событий в день, через 3 года удалить старое.**  
RANGE по `created_at` (месяц или день). Старый период снимается `DROP TABLE events_2023_01` без `DELETE` по строкам.

**Сценарий B — B2C / B2B / Enterprise, запросы фильтруют по типу.**  
LIST по `customer_type`. Pruning отсекает две лишние категории сразу.

**Сценарий C — равномерно разложить по `user_id`.**  
HASH по `user_id` с фиксированным modulus. Соседние пользователи не собираются в одну корзину.

**Сценарий D — аналитика заказов почти всегда по `created_at BETWEEN`.**  
RANGE по `created_at`. Диапазон дат совпадает с ключом, pruning оставляет один-два месяца.

**Сценарий E — платежи по странам EE/LV/LT/FI/SE.**  
LIST по коду страны. Набор значений конечный и стабильный, каждый отчёт «по стране» читает одну партицию.

---

# Часть 8. Партиционирование и индексы

```sql
CREATE INDEX idx_events_user_id ON events (user_id);
```

Индекс создан на родителе и автоматически появился на каждой партиции (в плане — `events_2026_09_10_user_id_idx`).

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM events
WHERE created_at >= '2026-09-10'
  AND created_at < '2026-09-11'
  AND user_id = 12345;
```

```
Index Scan using events_2026_09_10_user_id_idx on events_2026_09_10
  Index Cond: (user_id = 12345)
  Filter: (created_at >= ... AND created_at < ...)
Execution Time: 0.057 ms
```

### Анализ

1. **Pruning** оставил только `events_2026_09_10`. 9-е и 11-е даже не открывались.
2. **Индекс используется:** `Index Scan` / `Index Cond: (user_id = 12345)`.
3. **Уровень индекса.** Объявлен на родителе `lab03.events`, физически живёт на каждой партиции отдельным B-tree.
4. **Почему вместе эффективнее.** Partitioning отсекает дни, индекс внутри дня находит пользователя. Один индекс на 10 млн строк без партиций — большой B-tree и случайный heap. Одна партиция на день + локальный индекс — меньше страниц и выше локальность. Только partitioning без индекса по `user_id` дал бы Seq Scan дневной таблицы. Только индекс без partitioning искал бы по всей истории.

---

# Часть 9. Когда партиционирование не помогает

Запрос `WHERE event_type = 'click'` без индекса (часть 2): Append + 3 Seq Scan, **3.224 ms**, все партиции.

После `CREATE INDEX idx_events_event_type ON events (event_type)`:

```
Aggregate  (actual time=2.102..2.104)
  ->  Append
        ->  Bitmap Heap Scan on events_2026_09_09
              ->  Bitmap Index Scan on events_2026_09_09_event_type_idx
        ->  Bitmap Heap Scan on events_2026_09_10
        ->  Bitmap Heap Scan on events_2026_09_11
Execution Time: 2.200 ms
```

Индекс сменил Seq Scan на Bitmap Index Scan **внутри каждой** партиции, но Append по всем трём остался: pruning по-прежнему невозможен.

Партиционирование не решило проблему, потому что фильтр не по ключу партиции. `click` есть в каждом дне (~40% строк), так что даже индекс читает почти всю кучу — выигрыш скромный (3.2 → 2.2 ms).

**Вывод.** Партиционирование отвечает на вопрос «какую *часть таблицы* можно не открывать». Индекс отвечает на вопрос «как быстро найти строки *внутри* открытой части». Это разные оси оптимизации. Для `event_type` нужен индекс (или LIST по типу, если типов мало и запросы всегда режут по нему). Для «события за вчера» нужен RANGE по дате.

---

# Часть 10. Автоматическое создание партиций

Ночной job — расширение **`pg_cron`** на Primary, не cron хоста.

Образ `docker/postgres/Dockerfile` собирает `pg_cron` 1.6.4 в Bitnami PostgreSQL 15. В `conf.d/pg_cron.conf`:

```
shared_preload_libraries = 'pg_cron'
cron.database_name = 'library_db'
cron.timezone = 'Europe/Moscow'
```

Миграция `e5f6a7b8c9d0` включает расширение и ставит расписание:

```sql
SELECT cron.schedule('create-partitions', '0 1 * * *',
                     'SELECT maintain_partitions()');
SELECT cron.schedule('partition-health', '5 1 * * *',
                     'SELECT check_partition_health()');
```

`maintain_partitions()` — CreatePartitionsJob: горизонт сегодня + 3 дня для `lab03.events` и текущий месяц + 3 для `bookings`, создаёт только отсутствующие партиции, пишет `RAISE NOTICE` в формате методички. Повторный запуск безопасен.

Проверка, что job зарегистрирован:

```sql
SELECT jobid, jobname, schedule, command FROM cron.job;
```

Ручной прогон того же SQL, что вызывает pg_cron в 01:00:

```bash
docker compose exec postgres-primary \
  psql -U postgres -d library_db -c 'SELECT maintain_partitions();'
```

Либо `POST /admin/partitions/create` — backend вызывает ту же функцию.

---

# Часть 11. Сбой ночного job и alerting

`PartitionHealthCheck` — SQL-функция `check_partition_health()`, её в 01:05 вызывает `pg_cron`. Она проверяет и учебную `lab03.events`, и таблицу сервиса `bookings`. Канал уведомлений ночного прогона — таблица `partition_alert_log`. Повторный CRITICAL с тем же missing не пишется, переход в OK даёт recovery. Если проверку дергают через API, то же сообщение дополнительно пишется в `logs/partition_alerts.log` и при наличии токена уходит в Telegram.

### 11.2 Искусственная ошибка

Сначала job создал горизонт (на 2026-09-15 это дни `events_2026_09_15` … `events_2026_09_18` и месяцы `bookings_2026_09` … `bookings_2026_12`). Затем удалены дальние будущие партиции — как если бы ночной create не отработал:

```sql
SELECT maintain_partitions();

DROP TABLE lab03.events_2026_09_18;
DROP TABLE public.bookings_2026_12;

SELECT table_key, status, missing, alert_sent, alert_kind
FROM check_partition_health();
```

Первая проверка:

```
    table_key    |  status  |      missing      | alert_sent | alert_kind
-----------------+----------+-------------------+------------+------------
 lab03.events    | CRITICAL | events_2026_09_18 | t          | critical
 public.bookings | CRITICAL | bookings_2026_12  | t          | critical
```

Уведомление пришло в `partition_alert_log`:

```
🚨 Partition alert
Table: public.bookings
Missing partitions:
bookings_2026_12
Expected horizon: 3 months
Checked at:
2026-09-15 15:19:25
```

```
🚨 Partition alert
Table: lab03.events
Missing partitions:
events_2026_09_18
Expected horizon: 3 days
Checked at:
2026-09-15 15:19:25
```

Вторая проверка сразу после:

```
 lab03.events    | CRITICAL | events_2026_09_18 | f |
 public.bookings | CRITICAL | bookings_2026_12  | f |
```

`alert_sent=false` — тот же CRITICAL не дублируется.

Тот же сценарий с API: `POST /admin/partitions/demo/break` дропает дальнюю партицию и `events`, и `bookings`, затем вызывает ту же `check_partition_health()`.

### 11.3 Восстановление

```sql
SELECT maintain_partitions();
SELECT table_key, status, missing, alert_sent, alert_kind
FROM check_partition_health();
```

Job создала обе пропавшие партиции:

```
Created: events_2026_09_18, bookings_2026_12
```

Повторная проверка вернула OK и отправила recovery:

```
    table_key    | status | missing | alert_sent | alert_kind
-----------------+--------+---------+------------+------------
 lab03.events    | OK     |         | t          | recovery
 public.bookings | OK     |         | t          | recovery
```

```
🟢 Partition check OK
Table: public.bookings
All required partitions exist.
Checked at:
2026-09-15 15:19:29
```

```
🟢 Partition check OK
Table: lab03.events
All required partitions exist.
Checked at:
2026-09-15 15:19:29
```

В pgAdmin:

```sql
SELECT kind, table_key, message, created_at
FROM partition_alert_log
ORDER BY created_at DESC;
```

Четыре строки: `critical` × 2, затем `recovery` × 2.

Либо `POST /admin/partitions/demo/restore` — тот же `maintain_partitions()` + health.

### 11.4 Антишум

Состояние хранится в `partition_alert_state` (`table_key`, `last_notified_status`, `last_notified_missing`). Сценарий из методички воспроизведён на обеих таблицах: CRITICAL → alert, следующие CRITICAL → тишина, OK → recovery.

---

# Часть 12. Партиционирование собственного сервиса

## Шаг 1. Таблица

`bookings` — журнал выдач книг. На момент работы в ней **5 000 000** строк (2025-09-11 … 2026-09-11). Пользователи и книги — справочники, бронирования растут с каждым визитом.

## Шаг 2–4. Ключ, стратегия, обоснование

- **Ключ:** `created_at`. Почти все тяжёлые списки библиотекаря режутся по дате (`GET /api/bookings?from_date=&to_date=`). Старые выдачи можно будет снимать годом целиком.
- **Стратегия:** RANGE по **месяцу**. День дал бы сотни партиций на горизонте хранения; год слишком грубый для месячных отчётов. Месяц — около 400k строк при текущем потоке.
- **Какие запросы выигрывают от pruning:** список за период, фильтр `status + created_at`, любая аналитика «за сентябрь».
- **Какие не выигрывают:** `GET /api/bookings/{id}` (id не в ключе), `GET /api/books/popular` (нужны все выдачи).

Миграция `d4e5f6a7b8c9_partition_bookings.py`: новая таблица `PARTITION BY RANGE (created_at)`, PK `(id, created_at)` (требование PostgreSQL), копирование 5 млн строк, 16 месячных партиций с 2025-09 по 2026-12.

| Партиция | Строк |
| :--- | ---: |
| `bookings_2025_09` | 263 763 |
| `bookings_2025_10` … `bookings_2026_08` | ~384k–426k |
| `bookings_2026_09` | 147 243 |
| `bookings_2026_10` … `bookings_2026_12` | 0 (горизонт вперёд) |

Индексы объявлены на родителе и размножены по детям, в том числе `idx_bookings_status_created_at` и `idx_bookings_user_created`.

## Шаг 6. Реальные запросы API

### Запрос 1. `GET /api/bookings?from_date=2026-09-01&to_date=2026-09-30`

```sql
SELECT ... FROM bookings
WHERE created_at >= '2026-09-01' AND created_at < '2026-10-01'
ORDER BY created_at DESC
LIMIT 20;
```

```
Limit
  ->  Index Scan Backward using bookings_2026_09_created_at_idx
        on bookings_2026_09
        Index Cond: (created_at >= ... AND created_at < ...)
Execution Time: 0.093 ms
```

**Pruning есть:** открыт только сентябрь 2026. Остальные 15 партиций отсутствуют в плане.

Тот же список со `status=ACTIVE` идёт в `bookings_2026_09_status_created_at_idx`, **0.073 ms**.

### Запрос 2. `GET /api/bookings/{id}`

```sql
SELECT ... FROM bookings WHERE id = 4000000;
```

```
Append
  ->  Index Scan on bookings_2025_09 ... id = 4000000
  ->  Index Scan on bookings_2025_10
  ...
  ->  Index Scan on bookings_2026_09
  ->  Seq Scan on bookings_2026_10   -- пустые будущие
Execution Time: 0.448 ms
```

**Pruning нет.** `id` не входит в ключ RANGE, поэтому проверяются все партиции. Локальный индекс по `id` делает каждую проверку дешёвой (0.45 ms на 16 партициях), но при росте числа месяцев время будет расти. Это плата за партиционирование по дате.

### Запрос 3. `GET /api/books/popular`

```sql
SELECT books.id, books.title, books.author, COUNT(bookings.id)
FROM bookings JOIN books ON bookings.book_id = books.id
GROUP BY ...
ORDER BY booking_count DESC
LIMIT 10;
```

```
Limit
  ->  Sort
        ->  Finalize GroupAggregate
              ->  Parallel Append
                    ->  Parallel Seq Scan on bookings_2026_01
                    ->  Parallel Seq Scan on bookings_2026_03
                    ... все месяцы с данными ...
Execution Time: 623.434 ms
```

**Pruning нет и не должен быть:** топ книг считает всю историю. Партиционирование здесь не ускоряет запрос.


## Шаги 7–9. Автоматизация, контроль, alert

Те же SQL-функции `maintain_partitions()` / `check_partition_health()` обслуживают и `bookings`. Расписание — `pg_cron` на Primary. Алерты ночного прогона пишутся в `partition_alert_log`, дедупликация в `partition_alert_state`. Сценарий сбоя отработан на `events` и на `bookings` (часть 11): CRITICAL → тишина → recovery.


# Контрольные вопросы

1. **Что такое partitioning?** Разделение одной логической таблицы на несколько физических с общим именем. Приложение пишет в `bookings`, PostgreSQL кладёт строку в `bookings_2026_09`.
2. **Чем отличается от индекса?** Индекс — структура поиска внутри набора строк. Партиция — отдельный relfilenode, который можно не открывать или сбросить целиком. Индекс не позволяет `DROP` старый год за константное время.
3. **Стратегии PostgreSQL?** RANGE, LIST, HASH (и их комбинации — subquery partitions).
4. **Когда RANGE?** Есть естественный порядок и диапазонные запросы или TTL: даты, цены, id-диапазоны.
5. **Когда LIST?** Небольшое стабильное множество меток: тип клиента, страна, статус, tenant.
6. **Когда HASH?** Нужно равномерно размазать высококардинальный ключ, диапазоны по этому ключу не важны.
7. **Как выбрать partition key?** Он должен входить в частые `WHERE` и совпадать с границами жизненного цикла данных. Ключ обязан быть в PRIMARY KEY / UNIQUE.
8. **Что такое partition pruning?** Планировщик выкидывает партиции, которые по ограничению на ключ заведомо пусты. В плане остаётся одна-две дочерние таблицы.
9. **Почему pruning может не сработать?** Нет условия по ключу; ключ обёрнут в функцию (`DATE(created_at)` при ключе timestamp без совпадения); параметр не константа на этапе планирования (редко, зависит от `plan_cache_mode`); DEFAULT пересекается со всем.
10. **Можно ли использовать индексы вместе с partitioning?** Да, и нужно. Индекс на родителе создаёт индекс на каждой партиции.
11. **Если подходящей партиции нет?** `INSERT` падает с `no partition of relation found`. Отсюда job заранее и health-check.
12. **Зачем создавать будущие партиции заранее?** Чтобы ночная запись 00:01 не упала в пустоту. Горизонт страхует от разового сбоя job.
13. **Почему автоматизировать?** Иначе кто-то забудет 1 января / 1-го числа месяца. Ручное создание не масштабируется.
14. **Лог vs alert.** Лог пишет каждый прогон. Alert — сигнал человеку/дежурному, что нужна реакция.
15. **Recovery alert.** Сообщение, что проблема исчезла. Иначе инцидент «висит» в голове дежурного.
16. **Почему не слать один и тот же alert бесконечно?** Шум. Люди начинают игнорировать канал. Шлём на переход состояния и на смену списка missing.
17. **Всегда ли partitioning ускоряет запросы?** Нет. Запросы без ключа обходят все партиции (поиск по `id`, `COUNT` по всей истории). Мелкую таблицу партиционировать незачем: больше планирования, меньше пользы.
18. **Проблемы неверного размера партиций?** Слишком мелкие (день на годы вперёд) — сотни файлов, долгий planning, неудобный каталог. Слишком крупные (год) — pruning почти не режет, `DROP` грубый, вакуум и индексы снова огромные. В этом сервисе месяц ≈ 400k строк — разумный компромисс.

---

# Итог

Партиционирование — не одна команда `PARTITION BY`. В работе пройден весь цикл: RANGE/LIST/HASH на учебной схеме, pruning и его границы, индексы на партициях, перевод `bookings` (5 млн строк), nightly job, health-check, CRITICAL без спама и recovery. Индекс и партиция решают разные проблемы: вместе они ускоряют «выдачи за сентябрь», по отдельности не спасают `GET /books/popular`.
