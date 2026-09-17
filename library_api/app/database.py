from app.config import settings

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

replica_engine = None
ReplicaSessionLocal = None
if settings.DATABASE_REPLICA_URL:
    replica_engine = create_engine(settings.DATABASE_REPLICA_URL)
    ReplicaSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=replica_engine
    )


def get_db():
    """Primary: запись и запросы, которым нужна свежая транзакция."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_replica():
    """Replica: только SELECT. Если replica не настроена — падаем на Primary."""
    factory = ReplicaSessionLocal or SessionLocal
    db = factory()
    try:
        yield db
    finally:
        db.close()
