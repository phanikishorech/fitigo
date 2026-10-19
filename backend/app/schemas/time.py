"""Serialize absolute timestamps in IST without altering historical DB instants."""
from datetime import datetime
from pydantic import BaseModel, field_serializer
from app.core.time import as_ist


class ISTResponse(BaseModel):
    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_business_time(self, value):
        return as_ist(value).isoformat() if isinstance(value, datetime) else value