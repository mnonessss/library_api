from app.api import admin, bookings, books, reviews, shards, users
from app.database import get_db, get_db_replica
from app.sharding.pool import sharding_enabled, shard_engines

from fastapi import Depends, FastAPI, status
from fastapi.responses import JSONResponse

from sqlalchemy import text
from sqlalchemy.orm import Session


app = FastAPI(
    title='Library Scaling API',
    description='Backend для сервиса библиотеки',
    version='1.0.0'
)

app.include_router(users.router)
app.include_router(books.router)
app.include_router(bookings.router)
app.include_router(reviews.router)
app.include_router(admin.router)
app.include_router(shards.router)


def _db_role(db: Session) -> dict:
    row = db.execute(text(
        'SELECT inet_server_addr()::text, inet_server_port(), '
        'pg_is_in_recovery()'
    )).one()
    return {
        'addr': row[0],
        'port': row[1],
        'is_replica': bool(row[2]),
    }


@app.get('/health')
def health_check(
    db: Session = Depends(get_db),
    replica_db: Session = Depends(get_db_replica),
):
    try:
        payload = {
            'status': 'healthy',
            'primary': _db_role(db),
            'replica': _db_role(replica_db),
        }
        if sharding_enabled():
            shard_roles = []
            for index, engine in enumerate(shard_engines()):
                with engine.connect() as conn:
                    row = conn.execute(text(
                        'SELECT inet_server_addr()::text, '
                        'inet_server_port(), pg_is_in_recovery()'
                    )).one()
                    shard_roles.append({
                        'shard': index,
                        'addr': row[0],
                        'port': row[1],
                        'is_replica': bool(row[2]),
                    })
            payload['shards'] = shard_roles
        return payload
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={'status': 'unhealthy', 'error': str(e)},
        )
