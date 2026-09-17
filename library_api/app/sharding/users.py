from app.repositories.user_repository import UserRepository
from app.sharding.pool import (
    allocate_user_id,
    get_router,
    iter_shard_sessions,
    session_for_key,
    sharding_enabled,
)

from sqlalchemy import text


def list_users(skip: int, limit: int):
    rows = []
    for session in iter_shard_sessions():
        try:
            rows.extend(UserRepository(session).get_all(0, skip + limit))
        finally:
            session.close()
    rows.sort(key=lambda row: row.id)
    return rows[skip:skip + limit]


def count_users() -> int:
    total = 0
    for session in iter_shard_sessions():
        try:
            total += UserRepository(session).count()
        finally:
            session.close()
    return total


def create_user(name: str, email: str):
    user_id = allocate_user_id()
    db = session_for_key(user_id)
    try:
        return UserRepository(db).create(name, email, user_id=user_id)
    finally:
        db.close()


def shard_counts() -> list[dict]:
    result = []
    for index, session in enumerate(iter_shard_sessions()):
        try:
            users = session.execute(text('SELECT COUNT(*) FROM users')).scalar()
            result.append({
                'shard': index,
                'name': f'shard-{index}',
                'users': int(users or 0),
            })
        finally:
            session.close()
    return result


def lookup(user_id: int) -> dict:
    router = get_router()
    payload = {
        'user_id': user_id,
        'strategy': router.strategy,
        'shard_index': router.shard_index(user_id),
        'shard_name': router.shard_name(user_id),
        'n': router.n,
    }
    if sharding_enabled():
        db = session_for_key(user_id)
        try:
            row = UserRepository(db).get_by_id(user_id)
            payload['found'] = row is not None
        finally:
            db.close()
    return payload
