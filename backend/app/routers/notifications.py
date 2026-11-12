from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_role
from app.core.roles import ROLE_ADMIN, ROLE_SUPER_ADMIN
from app.database.session import get_db
from app.models.auth import User
from app.models.notification import NotificationEvent
from app.schemas.notification import NotificationEventResponse
from app.services.notification_service import NotificationService


def no_store(response: Response):
    response.headers['Cache-Control'] = 'no-store'


router = APIRouter(prefix="/notifications", dependencies=[Depends(no_store)])
from app.routers.notification_inbox import router as inbox_router
router.include_router(inbox_router)


def _to_response(ev: NotificationEvent) -> NotificationEventResponse:
    from app.services.notification_workflow import TEMPLATES
    # Legacy payloads were unrestricted. Never echo raw templates/credentials.
    payload = {}
    try:
        raw = json.loads(ev.payload_json or '{}')
        if isinstance(raw, dict):
            payload = {k:v for k,v in raw.items() if k in {'resource_id','gym_id','booking_id'} and type(v) is int and v>0}
    except (ValueError, TypeError): pass

    return NotificationEventResponse(
        id=ev.id,
        user_id=ev.user_id,
        event_type=ev.event_type if ev.event_type in TEMPLATES else 'LEGACY_EVENT',
        status=ev.status,
        payload=payload,
        error_message='DELIVERY_NOT_CONFIRMED' if ev.error_message else None,
        created_at=ev.created_at,
        sent_at=ev.sent_at,
    )


@router.get("/me", response_model=list[NotificationEventResponse])
def list_my_events(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
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
    limit: int = Query(50, ge=1, le=100),
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
