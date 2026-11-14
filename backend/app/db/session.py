from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
# Registers the listener that applies the row-level security context at
# the start of every transaction. Removing it breaks tenant isolation.
from app.db import context as _session_context  # noqa: F401


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
