from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


if not settings.database_url:
    # Allow boot without DB configured; /health/db will report unhealthy.
    engine = None
else:
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
    )

SessionLocal = (
    sessionmaker(autocommit=False, autoflush=False, bind=engine)
    if engine is not None
    else None
)


def get_db():
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
