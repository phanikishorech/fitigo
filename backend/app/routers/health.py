from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse
from app.core.errors import log_failure, request_id
from sqlalchemy import text

from app.database.session import engine


router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/health/db")
def health_db(request: Request):
    """DB connectivity check.

    Returns healthy=false if DB is not reachable (does not raise stack traces).
    """

    if engine is None:
        return JSONResponse(status_code=503, content={'status': 'unavailable', 'db': {'healthy': False},
            'request_id': request_id(request.scope)}, headers={'Cache-Control': 'no-store'})

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": {"healthy": True}}
    except Exception as exc:
        log_failure(request.scope, exc)
        return JSONResponse(status_code=503, content={'status': 'unavailable', 'db': {'healthy': False},
            'request_id': request_id(request.scope)}, headers={'Cache-Control': 'no-store'})
