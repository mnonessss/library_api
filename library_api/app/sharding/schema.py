from sqlalchemy import text
from sqlalchemy.orm import Session

USERS_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL,
    email VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
)
"""

BOOKINGS_DDL = """
CREATE TABLE IF NOT EXISTS bookings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    status VARCHAR NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    returned_at TIMESTAMPTZ
)
"""

REVIEWS_DDL = """
CREATE TABLE IF NOT EXISTS reviews (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    rating INTEGER,
    comment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
)
"""


def init_shard_schema(db: Session) -> None:
    db.execute(text(USERS_DDL))
    db.execute(text(
        'CREATE INDEX IF NOT EXISTS ix_users_email ON users (email)'
    ))
    db.execute(text(BOOKINGS_DDL))
    db.execute(text(
        'CREATE INDEX IF NOT EXISTS ix_bookings_user_id '
        'ON bookings (user_id)'
    ))
    db.execute(text(REVIEWS_DDL))
    db.execute(text(
        'CREATE INDEX IF NOT EXISTS ix_reviews_user_id ON reviews (user_id)'
    ))
    db.commit()


def init_all_shards() -> int:
    from app.sharding.pool import iter_shard_sessions, sharding_enabled

    if not sharding_enabled():
        return 0
    count = 0
    for session in iter_shard_sessions():
        try:
            init_shard_schema(session)
            count += 1
        finally:
            session.close()
    return count
