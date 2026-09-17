from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.sharding.router import ShardRouter


_HOST_PORTS = {
    'postgres-shard-0:5432': '127.0.0.1:5470',
    'postgres-shard-1:5432': '127.0.0.1:5471',
    'postgres-shard-2:5432': '127.0.0.1:5472',
    'postgres-shard-3:5432': '127.0.0.1:5473',
}


def _rewrite_url_for_host(url: str) -> str:
    if Path('/.dockerenv').exists():
        return url
    rewritten = url
    for docker_host, local_host in _HOST_PORTS.items():
        rewritten = rewritten.replace(docker_host, local_host)
    return rewritten


def shard_urls() -> list[str]:
    return [_rewrite_url_for_host(url) for url in settings.shard_urls]


def sharding_enabled() -> bool:
    return bool(shard_urls())


@lru_cache(maxsize=1)
def shard_engines() -> tuple[Engine, ...]:
    return tuple(create_engine(url) for url in shard_urls())


@lru_cache(maxsize=1)
def shard_session_factories() -> tuple[sessionmaker, ...]:
    return tuple(
        sessionmaker(autocommit=False, autoflush=False, bind=engine)
        for engine in shard_engines()
    )


@lru_cache(maxsize=1)
def get_router() -> ShardRouter:
    urls = shard_urls()
    return ShardRouter(
        n=len(urls),
        strategy=settings.SHARD_STRATEGY,
        virtual_nodes=settings.SHARD_VIRTUAL_NODES,
    )


def shard_index_for_key(key) -> int:
    return get_router().shard_index(key)


def session_for_key(key) -> Session:
    factories = shard_session_factories()
    return factories[shard_index_for_key(key)]()


def iter_shard_sessions() -> list[Session]:
    return [factory() for factory in shard_session_factories()]


def get_db_for_user(user_id: int):
    """Запись и чтение пользователя на его shard"""
    if sharding_enabled():
        db = session_for_key(user_id)
    else:
        from app.database import SessionLocal
        db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def allocate_user_id() -> int:
    if not sharding_enabled():
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            value = db.execute(
                text('SELECT COALESCE(MAX(id), 0) FROM users')
            ).scalar()
            return int(value or 0) + 1
        finally:
            db.close()

    max_id = 0
    for session in iter_shard_sessions():
        try:
            value = session.execute(
                text('SELECT COALESCE(MAX(id), 0) FROM users')
            ).scalar()
            max_id = max(max_id, int(value or 0))
        finally:
            session.close()
    return max_id + 1
