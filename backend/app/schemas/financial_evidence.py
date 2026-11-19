"""Future internal source-producer contract; deliberately not an HTTP input."""
from datetime import datetime
from typing import Literal
from pydantic import ConfigDict, Field, model_validator
from app.schemas.accounting_policy import Contract, Context


class FinancialSourceEvidence(Contract):
    model_config = ConfigDict(frozen=True)
    evidence_version: Literal[1] = 1
    checkout_id: str = Field(min_length=1, max_length=36)
    source_type: str = Field(min_length=1, max_length=40)
    source_id: str = Field(min_length=1, max_length=100)
    context: Context
    environment: Literal['test', 'live']
    environment_source: Literal['PAYMENT_CHECKOUT']
    occurred_at: datetime
    gym_id: int | None = Field(None, gt=0)
    owner_id_at_event: int | None = Field(None, gt=0)
    ownership_evidence_reference: str | None = Field(None, min_length=3, max_length=200)
    original_purchaser_id: int = Field(gt=0)
    holder_id_at_event: int | None = Field(None, gt=0)
    financial_beneficiary_id: int | None = Field(None, gt=0)
    beneficiary_evidence_reference: str | None = Field(None, min_length=3, max_length=200)
    agreement_pin_id: int | None = Field(None, gt=0)

    @model_validator(mode='after')
    def explicit_evidence(self):
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError('Source occurrence requires a timezone.')
        if bool(self.owner_id_at_event) != bool(self.ownership_evidence_reference):
            raise ValueError('Historical owner requires immutable ownership evidence, not current gym ownership.')
        if bool(self.financial_beneficiary_id) != bool(self.beneficiary_evidence_reference):
            raise ValueError('Financial beneficiary requires entitlement evidence.')
        if self.owner_id_at_event and self.gym_id is None:
            raise ValueError('Gym owner snapshot requires gym identity.')
        return self