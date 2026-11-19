"""Consolidated commercial configuration; not approval to post or pay."""
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import Field, StrictBool, model_validator
from app.schemas.financial_agreement import Money, Sharing, StrictModel


class PercentageSettings(StrictModel):
    revenue: Sharing
    gateway_fee: Sharing


class MonthlyVolumeSettings(StrictModel):
    method: Literal['MONTHLY_VERIFIED_VISIT_VOLUME'] = 'MONTHLY_VERIFIED_VISIT_VOLUME'
    reference_amount: Money = Decimal('3000.00')
    reference_visits: Annotated[int, Field(strict=True, gt=0, le=1000000000)] = 100
    gateway_fee: Sharing = Field(default_factory=lambda: Sharing(gym_percent=0, fitigo_percent=100))
    # Deliberately unresolved. None is neither zero nor a selected commercial rule.
    period_timezone: Literal['Asia/Kolkata'] | None = None
    rounding: Literal['MONTHLY_TOTAL_HALF_UP'] | None = None
    version_boundary: Literal['PIN_AT_ADMISSION'] | None = None
    purchase_fee_attribution: Literal['MEMBERSHIP_COMPLETE_EQUAL_VISITS'] | None = None
    invalidated_visit_correction: Literal['APPEND_ONLY_SOURCE_BACKED'] | None = None
    fitigo_earnings: Literal['NOT_APPROVED'] = 'NOT_APPROVED'


class SettlementSettings(StrictModel):
    booking_cycle: Literal['WEEKLY', 'MONTHLY'] | None = None
    multi_gym_cycle: Literal['MONTHLY'] | None = None
    minimum_payout: Money | None = None
    admin_approval_required: Literal[True] = True
    automatic_transfers: Literal[False] = False
    single_gym_cycle: Literal['UPFRONT', 'WEEKLY', 'MONTHLY'] | None = None
    cutoff_time: str | None = Field(None, pattern=r'^([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$')
    timezone: Literal['Asia/Kolkata', 'UTC'] | None = None
    weekly_cutoff_day: Annotated[int, Field(strict=True, ge=0, le=6)] | None = None
    monthly_cutoff_day: Annotated[int, Field(strict=True, ge=1, le=31)] | None = None
    short_month: Literal['LAST_CALENDAR_DAY', 'NEXT_MONTH'] | None = None
    holding_days: Annotated[int, Field(strict=True, ge=0, le=3660)] | None = None
    eligible_deductions: list[Literal['ACTUAL_TAX_WITHHOLDING', 'APPROVED_SOURCE_ADJUSTMENT']] | None = None
    payout_eligibility: Literal['VERIFIED_NET_SOURCE_UNDISPUTED'] | None = None
    partial_settlement: Literal['ALLOW_WITH_ALLOCATION_LINKS', 'FULL_ENTITLEMENT_ONLY'] | None = None
    failed_settlement: Literal['REMAIN_OUTSTANDING_REQUIRE_EVIDENCE'] | None = None

    @model_validator(mode='after')
    def unique_deductions(self):
        if self.eligible_deductions is not None and len(set(self.eligible_deductions)) != len(self.eligible_deductions):
            raise ValueError('Permitted deductions must be unique; an empty list explicitly means none.')
        return self


def percentage(gym, fitigo):
    return PercentageSettings(revenue=Sharing(gym_percent=gym, fitigo_percent=fitigo),
        gateway_fee=Sharing(gym_percent=50, fitigo_percent=50))


class GymFinancialSettings(StrictModel):
    contract_version: Literal[1] = 1
    individual: PercentageSettings = Field(default_factory=lambda: percentage(85, 15))
    single_gym: PercentageSettings = Field(default_factory=lambda: percentage(85, 15))
    no_show: PercentageSettings = Field(default_factory=lambda: percentage(70, 30))
    multi_gym: MonthlyVolumeSettings = Field(default_factory=MonthlyVolumeSettings)
    settlements: SettlementSettings = Field(default_factory=SettlementSettings)
    single_gym_entitlement: Literal['UPFRONT_ON_VERIFIED_PURCHASE'] = 'UPFRONT_ON_VERIFIED_PURCHASE'
    no_show_eligibility: Literal['EXPLICIT_AUTHORIZATION_ONLY'] = 'EXPLICIT_AUTHORIZATION_ONLY'
    gateway_fee_basis: Literal['ACTUAL_PROVIDER_EVIDENCE_ONLY'] = 'ACTUAL_PROVIDER_EVIDENCE_ONLY'
    unknown_fee: Literal['GROSS_RECORDED_NET_PENDING'] = 'GROSS_RECORDED_NET_PENDING'
    wallet_gateway_fee: Literal['NONE'] = 'NONE'


class SettingsCreate(StrictModel):
    mode: Literal['test', 'live']
    gym_id: Annotated[int, Field(strict=True, gt=0)]
    expected_version: Annotated[int, Field(strict=True, ge=0)]
    expected_effective_version_id: Annotated[int, Field(strict=True, gt=0)] | None
    effective_from: datetime
    settings: GymFinancialSettings
    reason: str = Field(min_length=3, max_length=500)
    acknowledge_configuration_only: StrictBool
    acknowledge_legacy_replacement: StrictBool = False

    @model_validator(mode='after')
    def valid(self):
        value = self.effective_from
        if value.tzinfo is None or value.utcoffset() is None or value.microsecond or not 1970 <= value.year <= 9998:
            raise ValueError('Effective start requires an explicit timezone and whole-second precision.')
        if not self.acknowledge_configuration_only:
            raise ValueError('Acknowledge configuration only; saving does not enable allocations or payouts.')
        return self