"""partition bookings by created_at month and add alert state

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-12 18:10:00.000000

"""
from datetime import date
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_months(value: date, months: int) -> date:
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    return date(year, month, 1)


def _month_start(value) -> date:
    if hasattr(value, 'date'):
        value = value.date()
    return date(value.year, value.month, 1)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS partition_alert_state (
            table_key TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            missing TEXT NOT NULL DEFAULT '',
            last_notified_status TEXT,
            last_notified_missing TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))

    relkind = conn.execute(text("""
        SELECT c.relkind
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'bookings' AND n.nspname = 'public'
    """)).scalar()
    if relkind == 'p':
        return

    bounds = conn.execute(text("""
        SELECT min(created_at), max(created_at) FROM bookings
    """)).one()
    today = date.today()
    if bounds[0] is None:
        start = today.replace(day=1)
        end = _add_months(start, 4)
    else:
        start = _month_start(bounds[0])
        last_data = _month_start(bounds[1])
        horizon_end = _add_months(today.replace(day=1), 4)
        end = max(_add_months(last_data, 1), horizon_end)

    conn.execute(text("""
        CREATE TABLE bookings_partitioned (
            id INTEGER NOT NULL,
            user_id INTEGER NOT NULL REFERENCES users(id),
            book_id INTEGER NOT NULL REFERENCES books(id),
            status VARCHAR,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            returned_at TIMESTAMPTZ,
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
    """))

    cursor = start
    while cursor < end:
        nxt = _add_months(cursor, 1)
        name = f'bookings_{cursor:%Y_%m}'
        conn.execute(text(f"""
            CREATE TABLE {name}
            PARTITION OF bookings_partitioned
            FOR VALUES FROM ('{cursor.isoformat()}') TO ('{nxt.isoformat()}')
        """))
        cursor = nxt

    conn.execute(text('ALTER SEQUENCE bookings_id_seq OWNED BY NONE'))
    conn.execute(text('SET session_replication_role = replica'))
    conn.execute(text("""
        INSERT INTO bookings_partitioned
            (id, user_id, book_id, status, created_at, returned_at)
        SELECT id, user_id, book_id, status, created_at, returned_at
        FROM bookings
    """))
    conn.execute(text('SET session_replication_role = DEFAULT'))
    conn.execute(text('DROP TABLE bookings'))
    conn.execute(text('ALTER TABLE bookings_partitioned RENAME TO bookings'))
    conn.execute(text("""
        ALTER TABLE bookings
        ALTER COLUMN id SET DEFAULT nextval('bookings_id_seq')
    """))
    conn.execute(text('ALTER SEQUENCE bookings_id_seq OWNED BY bookings.id'))
    conn.execute(text(
        'CREATE INDEX ix_bookings_id ON bookings (id)'
    ))
    conn.execute(text(
        'CREATE INDEX ix_bookings_user_id ON bookings (user_id)'
    ))
    conn.execute(text(
        'CREATE INDEX ix_bookings_book_id ON bookings (book_id)'
    ))
    conn.execute(text(
        'CREATE INDEX ix_bookings_status ON bookings (status)'
    ))
    conn.execute(text(
        'CREATE INDEX ix_bookings_created_at ON bookings (created_at)'
    ))
    conn.execute(text("""
        CREATE INDEX idx_bookings_status_created_at
        ON bookings (status, created_at)
    """))
    conn.execute(text("""
        CREATE INDEX idx_bookings_user_created
        ON bookings (user_id, created_at DESC)
    """))


def downgrade() -> None:
    raise NotImplementedError('Partitioned bookings cannot be auto-downgraded')
