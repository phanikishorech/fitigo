from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notification import NotificationEvent, NotificationStatus


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    def emit(self, *, user_id: int | None, event_type: str, payload: dict) -> NotificationEvent:
        ev = NotificationEvent(
            user_id=user_id,
            event_type=event_type,
            status=NotificationStatus.PENDING.value,
            payload_json=json.dumps(payload, default=str),
            error_message=None,
        )
        self.db.add(ev)
        self.db.flush()
        return ev

    def list_pending(self, *, limit: int = 50) -> list[NotificationEvent]:
        return list(
            self.db.execute(
                select(NotificationEvent)
                .where(NotificationEvent.status == NotificationStatus.PENDING.value)
                .order_by(NotificationEvent.id.asc())
                .limit(limit)
            )
            .scalars()
            .all()
        )

    def mark_sent(self, *, event_id: int) -> NotificationEvent:
        from fastapi import HTTPException
        raise HTTPException(409, 'Delivery status cannot be manually marked sent. Only the delivery worker records provider acceptance.')
