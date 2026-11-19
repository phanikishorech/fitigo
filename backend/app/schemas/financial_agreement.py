from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from app.schemas.accounting_policy import AccountingPolicy
from app.schemas.marketplace_allocation import MarketplacePolicy, VisitPayoutPolicy

Percent = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
Money = Annotated[Decimal, Field(ge=0, le=9999999999, max_digits=12, decimal_places=2)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)


class Sharing(StrictModel):
    gym_percent: Percent
    fitigo_percent: Percent

    @model_validator(mode='after')
    def total(self):
        if self.gym_percent + self.fitigo_percent != Decimal(100):
            raise ValueError('Gym and FitiGo percentages must total exactly 100.')
        return self


class MultiGymTerms(StrictModel):
    payout_per_visit: Money | None
    visits_per_member_month: Annotated[int, Field(strict=True, ge=1, le=100000)] | None
    payout_cap_per_member_month: Money | None


class SettlementTerms(StrictModel):
    booking_cycle: Literal['WEEKLY', 'MONTHLY']
    multi_gym_cycle: Literal['WEEKLY', 'MONTHLY']
    monthly_single_cycle: Literal['NEXT_CYCLE', 'UPFRONT']
    quarterly_single_cycle: Literal['NEXT_CYCLE', 'UPFRONT']
    half_yearly_single_cycle: Literal['NEXT_CYCLE', 'UPFRONT']
    yearly_single_cycle: Literal['NEXT_CYCLE', 'UPFRONT']
    minimum_payout: Money
    admin_approval_required: Literal[True]


class AgreementTerms(StrictModel):
    policy_contract: AccountingPolicy | None = None
    marketplace_contract: MarketplacePolicy | None = None
    visit_payout_contract: VisitPayoutPolicy | None = None
    attended: Sharing
    no_show: Sharing
    single_gym: Sharing
    multi_gym: MultiGymTerms
    settlements: SettlementTerms
    sharing_basis: Literal['AFTER_DISCOUNTS_EXCLUDING_TAX']
    gateway_fees: Literal['SEPARATE_ACTUAL']
    wallet_same_agreement: Literal[True]
    group_basis: Literal['ATTENDED_VISITORS_WHEN_UNIT_PRICED']
    business_model: Literal['AGENT_MARKETPLACE']
    membership_recognition: Literal['NOT_APPROVED']

    @model_validator(mode='after')
    def approved_contract_complete(self):
        if self.visit_payout_contract and self.visit_payout_contract.approval.status == 'APPROVED':
            if any(value is None for value in (self.multi_gym.payout_per_visit,self.multi_gym.visits_per_member_month,self.multi_gym.payout_cap_per_member_month)):
                raise ValueError('Approved visit payout requires an explicit rate, member/gym visit limit and payout cap.')
        if self.policy_contract:
            from app.services.accounting_policy import policy_readiness
            report = policy_readiness(self.model_dump(mode='json'))
            for name, section in report['sections'].items():
                if name in ('monetary', 'attended', 'no_show', 'single_gym', 'multi_gym', 'settlements'):
                    if getattr(self.policy_contract, name).approval.status == 'APPROVED' and section['missing_fields']:
                        raise ValueError(f'{name} approval requires all fields: {", ".join(section["missing_fields"])}')
        return self


class AgreementCreate(StrictModel):
    mode: Literal['test', 'live']
    gym_id: Annotated[int, Field(strict=True, gt=0)] | None = None
    expected_version: Annotated[int, Field(strict=True, ge=0)]
    effective_from: datetime
    effective_to: datetime | None = None
    action: Literal['AGREEMENT', 'INHERIT'] = 'AGREEMENT'
    terms: AgreementTerms | None = None
    agreement_reference: str = Field(min_length=3, max_length=200)
    reason: str = Field(min_length=3, max_length=500)
    ca_status: Literal['PENDING', 'RECORDED_APPROVAL'] = 'PENDING'
    ca_reference: str | None = Field(default=None, min_length=3, max_length=200)
    acknowledge_configuration_only: StrictBool

    @model_validator(mode='after')
    def valid(self):
        for value in (self.effective_from, self.effective_to):
            if value and (value.tzinfo is None or value.utcoffset() is None or value.microsecond):
                raise ValueError('Effective times require an explicit timezone and whole-second precision.')
            if value and not 1970 <= value.year <= 9998:
                raise ValueError('Effective dates are outside the supported range.')
        if self.effective_to and self.effective_to <= self.effective_from:
            raise ValueError('End must be after start; end is exclusive.')
        if self.action == 'AGREEMENT' and self.terms is None:
            raise ValueError('Agreement terms are required.')
        if self.action == 'INHERIT' and (self.gym_id is None or self.terms is not None or self.effective_to is not None):
            raise ValueError('Inherit is a gym-only version without terms or end date.')
        if (self.ca_status == 'RECORDED_APPROVAL') != bool(self.ca_reference):
            raise ValueError('Recorded CA approval requires a reference; pending review must not have an approval reference.')
        if not self.acknowledge_configuration_only:
            raise ValueError('Acknowledge that settings do not post commissions or enable statutory reports.')
        return self