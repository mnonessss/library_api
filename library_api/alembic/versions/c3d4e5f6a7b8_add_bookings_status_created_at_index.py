"""add bookings status created_at composite index

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-09-10 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'idx_bookings_status_created_at',
        'bookings',
        ['status', 'created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('idx_bookings_status_created_at', table_name='bookings')
