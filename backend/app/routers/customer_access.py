from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.dependencies import require_role
from app.core.roles import ROLE_CUSTOMER
from app.database.session import get_db
from app.models.auth import User
from app.schemas.access import AccessCalendarResponse, TodayAccessResponse
from app.services.access_service import AccessService


router = APIRouter(prefix="/customer")


@router.get("/access-calendar", response_model=AccessCalendarResponse)
def get_access_calendar(
    response: Response,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_CUSTOMER})),
):
    response.headers["Cache-Control"] = "no-store"
    svc = AccessService(db)
    return svc.calendar_month(user_id=current_user.id, year=year, month=month)


@router.get("/access/today", response_model=TodayAccessResponse)
def get_today_access(
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_CUSTOMER})),
):
    response.headers["Cache-Control"] = "no-store"
    svc = AccessService(db)
    return svc.get_today_access(user_id=current_user.id)
