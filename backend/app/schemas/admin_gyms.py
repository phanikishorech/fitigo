from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AdminGymListItem(BaseModel):
    id: int
    owner_user_id: int
    name: str
    city: str | None
    status: str
    is_active: bool
    is_featured: bool
    created_at: datetime
