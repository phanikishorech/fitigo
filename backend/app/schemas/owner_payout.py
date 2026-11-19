from datetime import datetime
from typing import Literal
from pydantic import Field, model_validator
from app.schemas.accounting_policy import Contract,Money


class PayoutItemInput(Contract):
    allocation_id: str | None = Field(None,min_length=36,max_length=36)
    visit_payout_id: str | None = Field(None,min_length=36,max_length=36)
    amount: Money

    @model_validator(mode='after')
    def valid(self):
        if bool(self.allocation_id)==bool(self.visit_payout_id) or self.amount<=0:raise ValueError('One source and a positive claim amount are required.')
        return self


class PayoutDeduction(Contract):
    kind: Literal['ACTUAL_TAX_WITHHOLDING','APPROVED_SOURCE_ADJUSTMENT']
    amount: Money
    reason: str = Field(min_length=3,max_length=500)
    evidence_reference: str = Field(min_length=3,max_length=200)


class PayoutCreate(Contract):
    items: list[PayoutItemInput] = Field(min_length=1,max_length=100)
    deductions: list[PayoutDeduction] = Field(default_factory=list,max_length=20)
    reason: str = Field(min_length=3,max_length=500)


class ActualPayoutEvidence(Contract):
    reference: str = Field(min_length=3,max_length=100,pattern=r'^[A-Za-z0-9_:/.-]+$')
    paid_at: datetime
    amount: Money
    currency: Literal['INR']
    source: Literal['BANK_STATEMENT','PROVIDER_EXPORT']
    document_reference: str = Field(min_length=3,max_length=200)
    owner_user_id: int = Field(strict=True,gt=0)

    @model_validator(mode='after')
    def timestamp(self):
        if self.paid_at.tzinfo is None or self.paid_at.utcoffset() is None or self.paid_at.microsecond:
            raise ValueError('Actual payment time requires timezone and whole-second precision.')
        if self.amount<=0:raise ValueError('Actual payment amount must be positive.')
        return self


class PayoutTransition(Contract):
    expected_version: int = Field(strict=True,ge=1)
    status: Literal['APPROVED','PROCESSING','PAID','FAILED','PENDING_APPROVAL','REVERSED']
    reason: str = Field(min_length=3,max_length=500)
    payment_evidence: ActualPayoutEvidence | None = None