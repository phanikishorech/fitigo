from __future__ import annotations
from app.schemas.time import ISTResponse

from datetime import datetime

from pydantic import BaseModel, Field


class WalletBalanceResponse(ISTResponse):
    balance: str
    currency: str = "INR"


class WalletTopupRequest(BaseModel):
    amount: float = Field(ge=1)
    currency: str = "INR"
    description: str | None = None


class WalletTransactionResponse(ISTResponse):
    id: int
    direction: str
    txn_type: str
    amount: str
    currency: str
    reference: str | None = None
    description: str | None = None
    created_at: datetime


class WalletTopupResponse(ISTResponse):
    transaction: WalletTransactionResponse
    balance: str
    currency: str = "INR"


class WalletTransactionsResponse(ISTResponse):
    balance: str
    currency: str = "INR"
    transactions: list[WalletTransactionResponse]
