"""Phase 2 contracts only. Choices describe policy, not implemented calculators."""
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

def exact_decimal_input(value):
    if isinstance(value, (float, bool)):
        raise ValueError('Money and percentages require decimal strings, integers or Decimal, never binary float/bool.')
    return value


Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2), BeforeValidator(exact_decimal_input)]
Percent = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2), BeforeValidator(exact_decimal_input)]
Reference = Annotated[str, Field(min_length=3, max_length=200)]
Context = Literal['BOOKING_PURCHASE', 'BOOKING_ATTENDANCE', 'NO_SHOW', 'MEMBERSHIP_PURCHASE',
                  'MEMBERSHIP_ACTIVATION', 'MEMBERSHIP_RECOGNITION', 'MULTI_GYM_VISIT']
Instant = Literal['CHECKOUT_CREATED', 'PAYMENT_CAPTURED', 'BOOKING_START', 'CHECKIN', 'NO_SHOW_CONFIRMED',
                  'MEMBERSHIP_ACTIVATED', 'RECOGNITION_PERIOD_START']
Rounding = Literal['HALF_UP', 'HALF_EVEN', 'DOWN']
Recognition = Literal['AT_ACTIVATION', 'DAILY_SERVICE_PERIOD', 'PER_VERIFIED_EVENT', 'OTHER_APPROVED']


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)


class Approval(Contract):
    status: Literal['AWAITING_APPROVAL', 'APPROVED'] = 'AWAITING_APPROVAL'
    reference: Reference | None = None

    @model_validator(mode='after')
    def evidence_required(self):
        if (self.status == 'APPROVED') != bool(self.reference):
            raise ValueError('Approved policy requires a reference; awaiting approval must not claim one.')
        return self


class PolicySection(Contract):
    approval: Approval = Field(default_factory=Approval)


class MonetaryPolicy(PolicySection):
    currency: Literal['INR'] = 'INR'
    storage_scale: Literal[2] = 2
    provider_unit: Literal['PAISE'] = 'PAISE'
    calculation_precision: Literal[28] = 28
    rounding: Rounding | None = None
    rounding_stage: Literal['PER_VISITOR', 'PER_BOOKING', 'PER_ALLOCATION'] | None = None
    residual_paise: Literal['LARGEST_REMAINDER_VISITOR_INDEX', 'FINAL_VISITOR', 'REQUIRE_EXACT'] | None = None
    discount_allocation: Literal['PROPORTIONAL_UNIT_PRICE', 'EXPLICIT_SOURCE_LINES'] | None = None
    tax_treatment: Literal['EXCLUDE_SEPARATELY_COLLECTED_TAX'] | None = None
    partial_refund: Literal['REVERSE_ORIGINAL_ALLOCATIONS', 'EXPLICIT_APPROVED_LINES'] | None = None


class AttendedPolicy(PolicySection):
    allocation_basis: Literal['PAID_NET_OF_DISCOUNTS_EXCLUDING_TAX'] | None = None
    calculation_unit: Literal['PER_ATTENDED_VISITOR', 'PER_BOOKING'] | None = None
    eligibility: Literal['VERIFIED_BACKEND_CHECKIN'] | None = None
    rounding: Rounding | None = None


class NoShowPolicy(PolicySection):
    allocation_basis: Literal['PAID_NET_OF_DISCOUNTS_EXCLUDING_TAX'] | None = None
    eligibility: Literal['CONFIRMED_PAID_CLOSED_WINDOW_NO_SCAN'] | None = None
    partial_attendance: Literal['BLOCK_FOR_REVIEW', 'UNATTENDED_VISITORS_ONLY'] | None = None
    rounding: Rounding | None = None


class MembershipPolicy(PolicySection):
    recognition_method: Recognition | None = None
    other_method_reference: Reference | None = None
    start_event: Literal['ACTIVATION', 'SERVICE_PERIOD_START'] | None = None
    end_event: Literal['ORIGINAL_EXPIRY', 'ADJUSTED_EXPIRY'] | None = None
    pause_treatment: Literal['SUSPEND_AND_EXTEND', 'CONTINUE_SCHEDULE'] | None = None
    transfer_treatment: Literal['PRESERVE_SCHEDULE_NO_NEW_SALE', 'PROHIBITED'] | None = None
    refund_treatment: Literal['REVERSE_ORIGINAL_RECOGNITION', 'MANUAL_REVIEW'] | None = None

    @model_validator(mode='after')
    def compatible(self):
        if self.recognition_method == 'OTHER_APPROVED' and not self.other_method_reference:
            raise ValueError('Other recognition methods require a specification reference and remain unsupported.')
        if self.recognition_method != 'OTHER_APPROVED' and self.other_method_reference:
            raise ValueError('Other-method reference is only applicable to OTHER_APPROVED.')
        if self.pause_treatment == 'SUSPEND_AND_EXTEND' and self.end_event == 'ORIGINAL_EXPIRY':
            raise ValueError('Suspended and extended recognition cannot end at original expiry.')
        return self


class MultiGymPolicy(PolicySection):
    # Existing per-visit/per-member-per-gym values stay in terms.multi_gym.
    platform_monthly_payout_cap: Money | None = None
    platform_cap_scope: Literal['PER_MEMBERSHIP_ALL_GYMS', 'ALL_MEMBERSHIPS_ALL_GYMS'] | None = None
    cap_exhaustion: Literal['HOLD_FOR_REVIEW', 'STOP_FURTHER_ALLOCATION'] | None = None
    earning_formula: Literal['FIXED_PER_VERIFIED_VISIT', 'PERCENT_OF_NET_PURCHASE', 'OTHER_APPROVED'] | None = None
    earning_fixed_amount: Money | None = None
    earning_percent: Percent | None = None
    earning_formula_reference: Reference | None = None
    recognition_method: Recognition | None = None
    recognition_reference: Reference | None = None
    unused_value: Literal['REMAIN_UNALLOCATED', 'MANUAL_REVIEW', 'OTHER_APPROVED'] | None = None
    unused_value_reference: Reference | None = None
    monthly_reconciliation: Literal['ADMIN_APPROVED_VERIFIED_VISITS'] | None = None
    allocation_timezone: Literal['Asia/Kolkata', 'UTC'] | None = None

    @model_validator(mode='after')
    def formula_values(self):
        choices = {'FIXED_PER_VERIFIED_VISIT': 'earning_fixed_amount',
                   'PERCENT_OF_NET_PURCHASE': 'earning_percent', 'OTHER_APPROVED': 'earning_formula_reference'}
        chosen = choices.get(self.earning_formula)
        for field in choices.values():
            value = getattr(self, field)
            if field != chosen and value is not None: raise ValueError('Earning parameters must match the selected formula.')
        if chosen and getattr(self, chosen) is None: raise ValueError('Selected earning formula needs its explicit parameter.')
        if self.recognition_method == 'OTHER_APPROVED' and not self.recognition_reference:
            raise ValueError('Other recognition needs a specification reference.')
        if self.recognition_method != 'OTHER_APPROVED' and self.recognition_reference:
            raise ValueError('Recognition specification is only for OTHER_APPROVED.')
        if self.unused_value == 'OTHER_APPROVED' and not self.unused_value_reference:
            raise ValueError('Other unused-value treatment needs a specification reference.')
        if self.unused_value != 'OTHER_APPROVED' and self.unused_value_reference:
            raise ValueError('Unused-value specification is only for OTHER_APPROVED.')
        return self


class SettlementPolicy(PolicySection):
    weekly_cutoff_day: Annotated[int, Field(strict=True, ge=0, le=6)] | None = None
    monthly_cutoff_day: Annotated[int, Field(strict=True, ge=1, le=31)] | None = None
    short_month: Literal['LAST_CALENDAR_DAY', 'NEXT_MONTH'] | None = None
    cutoff_time: str | None = Field(None, pattern=r'^([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$')
    timezone: Literal['Asia/Kolkata', 'UTC'] | None = None
    holding_days: Annotated[int, Field(strict=True, ge=0, le=3660)] | None = None
    eligible_deductions: list[Literal['ACTUAL_GATEWAY_FEES', 'ACTUAL_TAX_WITHHOLDING', 'APPROVED_SOURCE_ADJUSTMENT']] | None = None
    partial_settlement: Literal['ALLOW_WITH_ALLOCATION_LINKS', 'FULL_ENTITLEMENT_ONLY'] | None = None
    failed_settlement: Literal['REMAIN_OUTSTANDING_REQUIRE_EVIDENCE'] | None = None

    @model_validator(mode='after')
    def unique_deductions(self):
        if self.eligible_deductions is not None and len(set(self.eligible_deductions)) != len(self.eligible_deductions):
            raise ValueError('Deductions must be unique; empty list explicitly means none.')
        return self


class SelectionRule(PolicySection):
    instant: Instant | None = None


class SelectionPolicies(Contract):
    BOOKING_PURCHASE: SelectionRule = Field(default_factory=SelectionRule)
    BOOKING_ATTENDANCE: SelectionRule = Field(default_factory=SelectionRule)
    NO_SHOW: SelectionRule = Field(default_factory=SelectionRule)
    MEMBERSHIP_PURCHASE: SelectionRule = Field(default_factory=SelectionRule)
    MEMBERSHIP_ACTIVATION: SelectionRule = Field(default_factory=SelectionRule)
    MEMBERSHIP_RECOGNITION: SelectionRule = Field(default_factory=SelectionRule)
    MULTI_GYM_VISIT: SelectionRule = Field(default_factory=SelectionRule)


ALLOWED_INSTANTS = {
    'BOOKING_PURCHASE': {'CHECKOUT_CREATED', 'PAYMENT_CAPTURED'},
    'BOOKING_ATTENDANCE': {'CHECKOUT_CREATED', 'PAYMENT_CAPTURED', 'BOOKING_START', 'CHECKIN'},
    'NO_SHOW': {'CHECKOUT_CREATED', 'PAYMENT_CAPTURED', 'BOOKING_START', 'NO_SHOW_CONFIRMED'},
    'MEMBERSHIP_PURCHASE': {'CHECKOUT_CREATED', 'PAYMENT_CAPTURED'},
    'MEMBERSHIP_ACTIVATION': {'CHECKOUT_CREATED', 'PAYMENT_CAPTURED', 'MEMBERSHIP_ACTIVATED'},
    'MEMBERSHIP_RECOGNITION': {'MEMBERSHIP_ACTIVATED', 'RECOGNITION_PERIOD_START'},
    'MULTI_GYM_VISIT': {'MEMBERSHIP_ACTIVATED', 'CHECKIN'},
}


class AccountingPolicy(Contract):
    contract_version: Literal[2] = 2
    monetary: MonetaryPolicy = Field(default_factory=MonetaryPolicy)
    attended: AttendedPolicy = Field(default_factory=AttendedPolicy)
    no_show: NoShowPolicy = Field(default_factory=NoShowPolicy)
    single_gym: MembershipPolicy = Field(default_factory=MembershipPolicy)
    multi_gym: MultiGymPolicy = Field(default_factory=MultiGymPolicy)
    settlements: SettlementPolicy = Field(default_factory=SettlementPolicy)
    selection: SelectionPolicies = Field(default_factory=SelectionPolicies)

    @model_validator(mode='after')
    def consistency(self):
        for context, allowed in ALLOWED_INSTANTS.items():
            rule = getattr(self.selection, context)
            if rule.instant is not None and rule.instant not in allowed: raise ValueError(f'Unsupported instant for {context}.')
            if rule.approval.status == 'APPROVED' and rule.instant is None: raise ValueError(f'{context} cannot approve an unset instant.')
        if self.attended.rounding and self.monetary.rounding and self.attended.rounding != self.monetary.rounding:
            raise ValueError('Attended rounding must match the monetary contract.')
        if self.no_show.rounding and self.monetary.rounding and self.no_show.rounding != self.monetary.rounding:
            raise ValueError('No-show rounding must match the monetary contract.')
        return self