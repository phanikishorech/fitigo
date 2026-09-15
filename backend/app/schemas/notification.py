from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class NotificationEventResponse(BaseModel):
    id: int
    user_id: int | None
    event_type: str
    status: str
    payload: dict
    error_message: str | None
    created_at: datetime
    sent_at: datetime | None
