import logging

from app.alerts import deliver
from app.database import SessionLocal

from sqlalchemy import text


logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def run_partition_health(
    today=None,
    targets=None,
    force: bool = False,
) -> list[dict]:
    """PartitionHealthCheck: та же SQL-функция, что и у pg_cron."""
    db = SessionLocal()
    try:
        if force:
            db.execute(text("""
                UPDATE partition_alert_state
                SET last_notified_status = NULL, last_notified_missing = NULL
            """))
        rows = db.execute(text('SELECT * FROM check_partition_health()')).fetchall()
        db.commit()
        reports = []
        for row in rows:
            missing = [part for part in (row[2] or '').split(',') if part]
            report = {
                'table': row[0],
                'status': row[1],
                'missing': missing,
                'alert_sent': bool(row[3]),
                'alert_kind': row[4],
                'message': row[5],
                'suppressed': (not row[3]) and row[1] == 'CRITICAL',
            }
            if report['alert_sent'] and report['message']:
                deliver(report['message'])
            logger.info(
                'Health %s: %s missing=%s alert_sent=%s suppressed=%s',
                report['table'],
                report['status'],
                report['missing'],
                report['alert_sent'],
                report['suppressed'],
            )
            reports.append(report)
        return reports
    finally:
        db.close()


if __name__ == '__main__':
    run_partition_health()
