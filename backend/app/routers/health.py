from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.database.session import engine


router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/health/db")
def health_db():
    """DB connectivity check.

    Returns healthy=false if DB is not reachable (does not raise stack traces).
    """

    if engine is None:
        return {"status": "ok", "db": {"healthy": False, "error": "DATABASE_URL not configured"}}

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": {"healthy": True}}
    except Exception as e:  # noqa: BLE001 - keep response safe/clean
        return {"status": "ok", "db": {"healthy": False, "error": str(e)}}
