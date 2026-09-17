import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.config import settings

from sqlalchemy import text
from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)


def _alert_log_path() -> Path:
    path = Path(settings.ALERT_LOG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def format_critical(check: dict) -> str:
    missing = '\n'.join(check['missing']) or '(none)'
    checked = check['checked_at']
    return (
        '🚨 Partition alert\n'
        f'Table: {check["table"]}\n'
        'Missing partitions:\n'
        f'{missing}\n'
        f'Expected horizon: {check["horizon"]} '
        f'{"days" if "events" in check["table"] else "months"}\n'
        f'Checked at:\n{checked}'
    )


def format_recovery(check: dict) -> str:
    return (
        '🟢 Partition check OK\n'
        f'Table: {check["table"]}\n'
        'All required partitions exist.\n'
        f'Checked at:\n{check["checked_at"]}'
    )


def send_file(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    line = f'[{stamp}]\n{message}\n\n'
    path = _alert_log_path()
    with path.open('a', encoding='utf-8') as handle:
        handle.write(line)
    logger.info('Alert written to %s', path)


def send_telegram(message: str) -> None:
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return
    payload = json.dumps({
        'chat_id': chat_id,
        'text': message,
    }).encode('utf-8')
    request = Request(
        f'https://api.telegram.org/bot{token}/sendMessage',
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urlopen(request, timeout=10) as response:
            response.read()
        logger.info('Telegram alert sent')
    except URLError as exc:
        logger.warning('Telegram alert failed: %s', exc)


def deliver(message: str) -> None:
    send_file(message)
    send_telegram(message)


def ensure_state_table(db: Session) -> None:
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS partition_alert_state (
            table_key TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            missing TEXT NOT NULL DEFAULT '',
            last_notified_status TEXT,
            last_notified_missing TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    db.commit()


def _load_state(db: Session, table_key: str) -> dict | None:
    row = db.execute(
        text("""
            SELECT status, missing, last_notified_status, last_notified_missing
            FROM partition_alert_state
            WHERE table_key = :table_key
        """),
        {'table_key': table_key},
    ).fetchone()
    if row is None:
        return None
    return {
        'status': row[0],
        'missing': row[1],
        'last_notified_status': row[2],
        'last_notified_missing': row[3],
    }


def _save_state(
    db: Session,
    table_key: str,
    status: str,
    missing: str,
    notified_status: str | None,
    notified_missing: str | None,
) -> None:
    db.execute(
        text("""
            INSERT INTO partition_alert_state (
                table_key, status, missing,
                last_notified_status, last_notified_missing, updated_at
            )
            VALUES (
                :table_key, :status, :missing,
                :notified_status, :notified_missing, now()
            )
            ON CONFLICT (table_key) DO UPDATE SET
                status = EXCLUDED.status,
                missing = EXCLUDED.missing,
                last_notified_status = EXCLUDED.last_notified_status,
                last_notified_missing = EXCLUDED.last_notified_missing,
                updated_at = now()
        """),
        {
            'table_key': table_key,
            'status': status,
            'missing': missing,
            'notified_status': notified_status,
            'notified_missing': notified_missing,
        },
    )
    db.commit()


def notify_health(db: Session, check: dict, force: bool = False) -> dict:
    """Send alert only on state change. force=True sends anyway."""
    ensure_state_table(db)
    table_key = check['table']
    missing = ','.join(check['missing'])
    status = check['status']
    state = _load_state(db, table_key) or {}
    last_status = state.get('last_notified_status')
    last_missing = state.get('last_notified_missing')

    should_send = force
    kind = None
    if status == 'CRITICAL' and (
        last_status != 'CRITICAL' or last_missing != missing
    ):
        should_send = True
        kind = 'critical'
    elif status == 'OK' and last_status == 'CRITICAL':
        should_send = True
        kind = 'recovery'

    sent = False
    if should_send:
        if status == 'CRITICAL':
            deliver(format_critical(check))
            kind = kind or 'critical'
        else:
            deliver(format_recovery(check))
            kind = kind or 'recovery'
        sent = True
        last_status = status
        last_missing = missing

    _save_state(db, table_key, status, missing, last_status, last_missing)
    return {
        **check,
        'alert_sent': sent,
        'alert_kind': kind,
        'suppressed': (not sent) and status == 'CRITICAL',
    }
