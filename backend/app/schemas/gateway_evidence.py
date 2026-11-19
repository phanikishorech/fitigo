"""Contract for future verified settlement imports. No importer or payout API."""
from datetime import datetime
from typing import Literal
from pydantic import Field, model_validator
from app.schemas.accounting_policy import Contract, Money


class GatewaySettlementEvidence(Contract):
    provider: Literal['RAZORPAY', 'CASHFREE']
    environment: Literal['test', 'live']
    provider_settlement_id: str = Field(min_length=1, max_length=100)
    provider_status: str = Field(default='UNAVAILABLE', min_length=1, max_length=50)
    provider_settlement_reference: str | None = Field(None, max_length=200)
    currency: Literal['INR']
    actual_settlement_amount: Money | None = None
    gateway_fee: Money | None = None
    gateway_fee_tax: Money | None = None
    fee_basis: Literal['INCLUDING_TAX', 'EXCLUDING_TAX', 'UNAVAILABLE'] = 'UNAVAILABLE'
    settled_at: datetime | None = None
    verified_at: datetime
    verification_source: Literal['AUTHENTICATED_PROVIDER_FETCH', 'VERIFIED_PROVIDER_EXPORT']
    reconciliation_status: Literal['UNRECONCILED', 'MATCHED', 'MISMATCH'] = 'UNRECONCILED'
    evidence_reference: str = Field(min_length=3, max_length=200)

    @model_validator(mode='after')
    def timestamps(self):
        for value in (self.settled_at, self.verified_at):
            if value and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError('Provider evidence timestamps require timezone.')
        if self.gateway_fee is not None and self.fee_basis == 'UNAVAILABLE':
            raise ValueError('Actual fee requires an explicit provider fee basis.')
        return self