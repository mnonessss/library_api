import logging

from app.database import SessionLocal

from sqlalchemy import text


logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def run_create_partitions(today=None, targets=None) -> list[dict]:
    """CreatePartitionsJob: SQL-функция, которую по ночам вызывает pg_cron."""
    db = SessionLocal()
    try:
        log = db.execute(text('SELECT maintain_partitions()')).scalar()
        db.commit()
        logger.info(log)
        return [{'table': 'all', 'log': log}]
    finally:
        db.close()


if __name__ == '__main__':
    run_create_partitions()
