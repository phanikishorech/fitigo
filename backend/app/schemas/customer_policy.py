from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.schemas.time import ISTResponse


class CancellationPolicy(ISTResponse):
    eligible: bool
    reason: str
    policy: str
    deadline: datetime | None = None
    scheduled_start: datetime | None = None
    refundable_amount: str = '0.00'
    currency: str
    wallet_credit_amount: str = '0.00'
    wallet_transaction_id: int | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None


class TransferPreviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    recipient_email: EmailStr


class TransferConfirmRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    confirmation_token: str = Field(min_length=20, max_length=2000)
    confirmed: Literal[True]