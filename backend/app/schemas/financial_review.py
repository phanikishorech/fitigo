from typing import Literal
from pydantic import Field,StrictBool
from app.schemas.financial_agreement import StrictModel


class ReviewCreate(StrictModel):
    mode: Literal['test','live']
    gym_id: int=Field(strict=True,gt=0)
    source_evidence_id: str=Field(min_length=36,max_length=36)
    kind: Literal['LATE_VISIT','MONTH_CORRECTION','CLOSED_FEE_BUDGET','RESERVED_OR_PAID']
    reason: str=Field(min_length=3,max_length=500)


class ReviewDecision(StrictModel):
    mode: Literal['test','live']
    expected_revision: int=Field(strict=True,gt=0)
    status: Literal['APPROVED_FOR_RECONCILIATION','REJECTED','NEEDS_EVIDENCE']
    reason: str=Field(min_length=3,max_length=500)
    acknowledge_reserved_paid: StrictBool=False
    acknowledge_no_execution: StrictBool
    expected_impact_hash: str=Field(min_length=64,max_length=64)


class ReviewExecution(StrictModel):
    mode: Literal['test','live']
    expected_revision: int=Field(strict=True,gt=0)
    expected_impact_hash: str=Field(min_length=64,max_length=64)
    authorization_reference: str=Field(min_length=3,max_length=200)
    reason: str=Field(min_length=3,max_length=500)
    authorize_execution: StrictBool