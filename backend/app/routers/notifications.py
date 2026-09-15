from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_role
from app.core.roles import ROLE_ADMIN, ROLE_SUPER_ADMIN
from app.database.session import get_db
from app.models.auth import User
from app.models.notification import NotificationEvent
from app.schemas.notification import NotificationEventResponse
from app.services.notification_service import NotificationService


router = APIRouter(prefix="/notifications")


def _to_response(ev: NotificationEvent) -> NotificationEventResponse:
    try:
        payload = json.loads(ev.payload_json or "{}")
    except Exception:
        payload = {"_raw": ev.payload_json}

    return NotificationEventResponse(
        id=ev.id,
        user_id=ev.user_id,
        event_type=ev.event_type,
        status=ev.status,
        payload=payload,
        error_message=ev.error_message,
        created_at=ev.created_at,
        sent_at=ev.sent_at,
    )


@router.get("/me", response_model=list[NotificationEventResponse])
def list_my_events(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = 50,
    offset: int = 0,
):
    items = (
        db.execute(
            select(NotificationEvent)
            .where(NotificationEvent.user_id == current_user.id)
            .order_by(NotificationEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return [_to_response(e) for e in items]


@router.get("/pending", response_model=list[NotificationEventResponse])
def list_pending(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_ADMIN, ROLE_SUPER_ADMIN})),
    limit: int = 50,
):
    svc = NotificationService(db)
    items = svc.list_pending(limit=limit)
    return [_to_response(e) for e in items]


@router.post("/{event_id}/mark-sent", response_model=NotificationEventResponse)
def mark_sent(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_ADMIN, ROLE_SUPER_ADMIN})),
):
    svc = NotificationService(db)
    ev = svc.mark_sent(event_id=event_id)
    return _to_response(ev)
