# Лабораторная 4. Масштабирование чтения PostgreSQL: Primary + Replica

## Часть 1. Поднять Primary и Replica

Фрагмент docker-compose, в котором поднимаются Primary и Replica:
```bash
  postgres-primary:
    image: bitnamilegacy/postgresql:15.9.0
    environment:
      POSTGRESQL_USERNAME: ${DB_USER}
      POSTGRESQL_PASSWORD: ${DB_PASSWORD}
      POSTGRESQL_DATABASE: ${DB_NAME}
      POSTGRESQL_REPLICATION_MODE: master
      POSTGRESQL_REPLICATION_USER: ${DB_USER}
      POSTGRESQL_REPLICATION_PASSWORD: ${DB_PASSWORD}
      POSTGRESQL_PRIMARY_PASSWORD: ${DB_PASSWORD}
    ports:
      - "${DB_PORT}:5432"
    volumes:
      - primary_data:/bitnami/postgresql 
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d ${DB_NAME}"]
      interval: 5s
      timeout: 5s
      retries: 5
    
  postgres-replica:
    image: bitnamilegacy/postgresql:15.9.0
    environment:
      POSTGRESQL_USERNAME: ${DB_USER}
      POSTGRESQL_PASSWORD: ${DB_PASSWORD}
      POSTGRESQL_DATABASE: ${DB_NAME}
      POSTGRESQL_MASTER_HOST: postgres-primary
      POSTGRESQL_MASTER_PORT_NUMBER: 5432
      POSTGRESQL_REPLICATION_MODE: slave
      POSTGRESQL_REPLICATION_USER: ${DB_USER}
      POSTGRESQL_REPLICATION_PASSWORD: ${DB_PASSWORD}
    ports:
      - "${DB_REPLICA_PORT}:5432"
    depends_on:
      postgres-primary:
        condition: service_healthy
    volumes:
      - replica_data:/bitnami/postgresql
```

postgres-primary - это Primary - контейнер, а postgres-replica - это Replica.

Чтобы подключиться к Primary:
```bash
docker exec -it library_api-postgres-primary-1 psql -U app_user -d app_db
```
Чтобы подключиться к Replica:
```bash
docker exec -it library_api-postgres-replica-1 psql -U app_user -d app_db
```

Пользователь и база берутся из `.env`: `postgres` / `library_db`. В команде обязательно должен быть `psql`, иначе Docker воспримет `-U` как имя программы.


## Часть 2. Настроить streaming replication
В нашем docker-compose.yml streaming настраивается автоматически на этапе инициализации контейнеров. Для проверки выполним подключение к Primary командой из пункта 1 и выполним команду:
```bash
SELECT pid, usename, application_name, client_addr, state, sync_state, replay_lag 
FROM pg_stat_replication;
```

Получили такой результат:

 pid | usename  | application_name | client_addr |   state   | sync_state | replay_lag 
 :---: | :---: | :---: |  :---: | :---: | :---: | :---: |
 152 | postgres | walreceiver      | 10.66.22.3  | streaming | async      | 
(1 row)

Streaming работает в дефолтном режиме async.


## Часть 3. Доказать, что репликация работает

На Primary я создала тестовую таблицу и добавила туда запись:

library_db=# CREATE TABLE test_replication (
library_db(#     id SERIAL PRIMARY KEY,
library_db(#     message TEXT,
library_db(#     created_at TIMESTAMP DEFAULT NOW()
library_db(# );
CREATE TABLE
library_db=# 
library_db=# INSERT INTO test_replication (message) VALUES ('Hello from Primary!');
INSERT 0 1

Далее я подключилась к Replica, выполнила запрос на получение всех данных из таблицы test_replication и получила следующее:
library_db=# SELECT * FROM test_replication;
 id |       message       |         created_at         
 :---: | :---: | :---: |
  1 | Hello from Primary! | 2026-09-13 10:16:19.964085


## Часть 4. Проверить read-only поведение Replica
При попытке вставить в Replica новую запись БД выдает ошибку:
```bash
library_db=# INSERT INTO test_replication(message) VALUES ('NEW ROW');
ERROR:  cannot execute INSERT in a read-only transaction
```

Replica не должна использоваться для записи, т.к. она является точной копией Primary. Если разрешить запись на Replica, то данные разойдутся при следующем применении WAL с Primary: возникнут критические конфликты и ошибки целостности данных.

## Часть 5. SELECT сервиса на Replica, запись на Primary

В backend заведены два движка SQLAlchemy.

`app/config.py` собирает URL Primary и Replica. В Docker Compose они задаются явно:

```yaml
environment:
  DATABASE_URL: postgresql://${DB_USER}:${DB_PASSWORD}@postgres-primary:5432/${DB_NAME}
  DATABASE_REPLICA_URL: postgresql://${DB_USER}:${DB_PASSWORD}@postgres-replica:5432/${DB_NAME}
```

`app/database.py`:

```python
engine = create_engine(settings.DATABASE_URL)          # Primary
SessionLocal = sessionmaker(bind=engine)

replica_engine = create_engine(settings.DATABASE_REPLICA_URL)  # Replica
ReplicaSessionLocal = sessionmaker(bind=replica_engine)

def get_db():          # запись и свежие транзакции
    ...

def get_db_replica():  # только SELECT
    ...
```

На Replica уходят каталог и профили — чистые SELECT:

| Эндпоинт | Сессия | Зачем |
| :--- | :--- | :--- |
| `GET /api/books/` | `get_db_replica` | каталог книг |
| `GET /api/books/popular` | `get_db_replica` | агрегация по каталогу |
| `GET /api/books/{id}` | `get_db_replica` | карточка книги |
| `GET /api/users/` | `get_db_replica` | список читателей |
| `GET /api/users/{id}` | `get_db_replica` | профиль читателя |

Запись (`POST`/`PUT`/`DELETE` книг, пользователей, бронирований, отзывов) и alembic по-прежнему используют `get_db` → Primary.

Фрагмент каталога:

```python
@router.get('/')
def get_books(..., db: Session = Depends(get_db_replica)):
    ...

@router.post('/')
def create_book(..., db: Session = Depends(get_db)):
    ...
```

Проверка через `GET /health`:

```json
{
  "status": "healthy",
  "primary": {"addr": "10.66.22.2/32", "port": 5432, "is_replica": false},
  "replica": {"addr": "10.66.22.3/32", "port": 5432, "is_replica": true}
}
```

Адреса разные: `10.66.22.2` — Primary (`pg_is_in_recovery() = false`), `10.66.22.3` — Replica (`true`). Это тот же `client_addr`, что был у `walreceiver` в части 2. `GET /api/books/` и `GET /api/users/` отвечают 200 с Replica.


## Часть 6. Понять replication lag
Воспроизвести replication lag - мне не удалось, у меня он слишком маленький


## Контрольные вопросы
### Вопрос 1. Чем Primary отличается от Replica?
Primary принимает операции INSERT/UPDATE/DELETE и генерирует WAL. Replica работает с операциями SELECT в режиме read - only, при этом непрерывно читая WAL и применяя его к своей таблице.

### Вопрос 2. Почему запись выполняем на Primary?
Потому что если начать записывать на Replica, то данные разойдутся с Primary и это приведет к конфликтам данных и ошибкам целостности.

### Вопрос 3. Как изменение из Primary попадает на Replica?
Primary пишет все изменения в WAL и транслирует этот WAL реплике. Replica читает и применяет полученные инструкции к своей таблице.

### Вопрос 4. Что такое WAL в контексте репликации?
WAL - это журнал последовательных логов, в который PostgreSQL записывает каждое изменение данных до того, как это изменение будет применено. Primary транслирует WAL реплике и реплика просто применяет записи из WAL к своим таблицам.

### Вопрос 5. Что такое replication lag?
Это задержка между моментом фиксации транзакции на Primary и моментом, когда эта запись становится доступной для чтения реплике

### Вопрос 6. Почему следующий SELECT после INSERT потенциально может увидеть старые данные, если его отправить на Replica?
Из - за replication lag. Пока WAL передастся с Primary на Replica и там применится, пройдет время, в это время SELECT на Replica будет видеть старые данные

### Вопрос 7. Что именно масштабируется при Read Scaling: скорость одного SQL-запроса или способность системы обслуживать больше чтений?
Масштабируется именно пропускная способность - способность обслужить больше чтений. Скорость выполнения одного тяжелого SELECT от добавления реплик не увеличится, т.к. реплике все равно придется делать всю ту же самую работу

### Вопрос 8. Почему наличие Replica не отменяет необходимость индексов и оптимизации SQL?
Потому что Replica - это просто копия Primary. Если запрос на Primary выполняется 10 сек, то и на реплике он будет выполняться 10 сек. Реплики не спасают от низкой производительности самих запросов, для этого как раз применяются индексы и оптимизации SQL

### Вопрос 9. Расскажите про CAP-теорему
Согласно CAP - теореме, одновременно можно добиться выполения только двух из трех пунктов:
C(Consistency) - все узлы видят одинаковые данные в один и тот же момент времени
A(Availability) - Система всегда отвечает на запросы, даже если какие - то узлы упали
P(Partition tolerance) - система работает даже при потере связи между узлами
