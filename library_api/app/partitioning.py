from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session


def add_months(value: date, months: int) -> date:
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    return date(year, month, 1)


@dataclass(frozen=True)
class PartitionTarget:
    schema: str
    table: str
    column: str
    granularity: str
    horizon: int
    name_prefix: str

    @property
    def qualified_table(self) -> str:
        return f'{self.schema}.{self.table}'

    @property
    def key(self) -> str:
        return self.qualified_table


EVENTS_DAILY = PartitionTarget(
    schema='lab03',
    table='events',
    column='created_at',
    granularity='day',
    horizon=3,
    name_prefix='events',
)

BOOKINGS_MONTHLY = PartitionTarget(
    schema='public',
    table='bookings',
    column='created_at',
    granularity='month',
    horizon=3,
    name_prefix='bookings',
)

MANAGED_TARGETS = (EVENTS_DAILY, BOOKINGS_MONTHLY)


class PartitionManager:
    def __init__(self, db: Session, today: date | None = None):
        self.db = db
        self.today = today or date.today()

    def required_periods(self, target: PartitionTarget) -> list[date]:
        if target.granularity == 'day':
            return [
                self.today + timedelta(days=offset)
                for offset in range(target.horizon + 1)
            ]
        if target.granularity == 'month':
            start = self.today.replace(day=1)
            return [add_months(start, offset) for offset in range(target.horizon + 1)]
        raise ValueError(f'Unknown granularity: {target.granularity}')

    def partition_name(self, target: PartitionTarget, period: date) -> str:
        if target.granularity == 'day':
            return f'{target.name_prefix}_{period:%Y_%m_%d}'
        return f'{target.name_prefix}_{period:%Y_%m}'

    def bounds(self, target: PartitionTarget, period: date) -> tuple[date, date]:
        if target.granularity == 'day':
            return period, period + timedelta(days=1)
        start = period.replace(day=1)
        return start, add_months(start, 1)

    def existing_names(self, target: PartitionTarget) -> list[str]:
        rows = self.db.execute(
            text("""
                SELECT child.relname
                FROM pg_inherits inh
                JOIN pg_class child ON child.oid = inh.inhrelid
                JOIN pg_class parent ON parent.oid = inh.inhparent
                JOIN pg_namespace nsp ON nsp.oid = parent.relnamespace
                WHERE parent.relname = :table
                  AND nsp.nspname = :schema
                ORDER BY child.relname
            """),
            {'table': target.table, 'schema': target.schema},
        ).fetchall()
        return [row[0] for row in rows]

    def missing_periods(self, target: PartitionTarget) -> list[date]:
        existing = set(self.existing_names(target))
        return [
            period
            for period in self.required_periods(target)
            if self.partition_name(target, period) not in existing
        ]

    def create_partition(self, target: PartitionTarget, period: date) -> str:
        name = self.partition_name(target, period)
        start, end = self.bounds(target, period)
        self.db.execute(
            text(f"""
                CREATE TABLE IF NOT EXISTS {target.schema}.{name}
                PARTITION OF {target.qualified_table}
                FOR VALUES FROM (:start_at) TO (:end_at)
            """),
            {'start_at': start, 'end_at': end},
        )
        return name

    def ensure_events_parent(self) -> None:
        self.db.execute(text('CREATE SCHEMA IF NOT EXISTS lab03'))
        self.db.execute(text("""
            CREATE TABLE IF NOT EXISTS lab03.events (
                id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                event_type VARCHAR(50) NOT NULL,
                payload TEXT,
                created_at TIMESTAMP NOT NULL
            ) PARTITION BY RANGE (created_at)
        """))

    def create_missing(self, target: PartitionTarget) -> dict:
        if target.table == 'events':
            self.ensure_events_parent()

        existing = self.existing_names(target)
        required = [
            self.partition_name(target, period)
            for period in self.required_periods(target)
        ]
        missing = self.missing_periods(target)
        created = []
        for period in missing:
            created.append(self.create_partition(target, period))
        self.db.commit()
        return {
            'table': target.qualified_table,
            'existing': existing,
            'required': required,
            'missing': [
                self.partition_name(target, period) for period in missing
            ],
            'created': created,
        }

    def health(self, target: PartitionTarget) -> dict:
        existing = self.existing_names(target)
        required = [
            self.partition_name(target, period)
            for period in self.required_periods(target)
        ]
        missing = [name for name in required if name not in existing]
        return {
            'table': target.qualified_table,
            'status': 'OK' if not missing else 'CRITICAL',
            'existing': existing,
            'required': required,
            'missing': missing,
            'horizon': target.horizon,
            'checked_at': datetime.now(timezone.utc).replace(microsecond=0),
        }

    def drop_partition(self, target: PartitionTarget, name: str) -> None:
        self.db.execute(text(f'DROP TABLE IF EXISTS {target.schema}.{name}'))
        self.db.commit()
