"""Commercial allocation inputs, separate from statutory recognition policy."""
from decimal import Decimal
from typing import Literal
from pydantic import ConfigDict, Field, model_validator
from app.schemas.accounting_policy import Approval, Contract, Money, Rounding


class MarketplacePolicy(Contract):
    """Optional on a NEW agreement version. No unknown commercial defaults."""
    contract_version: Literal[1] = 1
    approval: Approval = Field(default_factory=Approval)
    allocation_basis: Literal['SOURCE_PRICE_AFTER_DISCOUNTS_EXCLUDING_TAX'] | None = None
    price_representation: Literal['GROSS_BEFORE_DISCOUNT', 'ALREADY_DISCOUNTED'] | None = None
    tax_treatment: Literal['EXCLUDE_EVIDENCED_TAX'] | None = None
    rounding: Rounding | None = None
    visitor_residual: Literal['LOWEST_VISITOR_INDEX', 'FINAL_VISITOR', 'REQUIRE_EXACT'] | None = None
    # Contract choices encode the expressly approved business rules, not a rate
    # default for historical versions. Percentages remain in existing share fields.
    fee_split: Literal['EQUAL_ACTUAL_INCLUDING_FEE_TAX'] | None = None
    fee_residual: Literal['FITIGO', 'GYM_OWNER'] | None = None
    fee_before_payout: Literal['REQUIRED', 'ALLOW_PROVISIONAL_GROSS'] | None = None
    single_gym_entitlement: Literal['UPFRONT_ON_VERIFIED_PURCHASE'] | None = None
    # Still a policy choice: distributing one provider fee across a cart/visitors
    # must not charge the entire fee again on each successful admission.
    fee_distribution: Literal['PROPORTIONAL_GATEWAY_FUNDED_VALUE'] | None = None
    cancellation_reversal: Literal['FULL_ORIGINAL_ALLOCATION'] | None = None

    @model_validator(mode='after')
    def approval_completeness(self):
        if self.approval.status == 'APPROVED':
            required = ('allocation_basis', 'price_representation', 'tax_treatment', 'rounding',
                'visitor_residual', 'fee_split', 'fee_residual', 'fee_before_payout',
                'single_gym_entitlement', 'fee_distribution')
            missing = [key for key in required if getattr(self, key) is None]
            if missing: raise ValueError('Marketplace approval requires: ' + ', '.join(missing))
        return self


class VisitPayoutPolicy(Contract):
    contract_version: Literal[1] = 1
    approval: Approval = Field(default_factory=Approval)
    period_timezone: Literal['Asia/Kolkata', 'UTC'] | None = None
    platform_cap_mode: Literal['NOT_APPLICABLE', 'PER_MEMBERSHIP_ALL_GYMS', 'ALL_MEMBERSHIPS_ALL_GYMS'] | None = None
    platform_monthly_cap: Money | None = None
    cap_exhaustion: Literal['REJECT_WHOLE_VISIT', 'ALLOW_PARTIAL_TO_CAP'] | None = None
    cap_order: Literal['SERIALIZED_PROCESSING_ORDER'] | None = None
    # Fee responsibility for a purchase funding multiple visits is not implicitly
    # charged repeatedly. Separate evidence/distribution policy is required later.
    fee_readiness: Literal['HOLD_PAYOUT_PENDING_FEE_DISTRIBUTION'] | None = None

    @model_validator(mode='after')
    def valid(self):
        if self.platform_cap_mode == 'NOT_APPLICABLE' and self.platform_monthly_cap is not None:
            raise ValueError('No platform cap cannot include a cap amount.')
        if self.approval.status == 'APPROVED':
            if any(getattr(self,key) is None for key in ('period_timezone','platform_cap_mode','cap_exhaustion','cap_order','fee_readiness')):
                raise ValueError('Visit payout approval requires explicit monthly/cap/fee treatment.')
            if self.platform_cap_mode != 'NOT_APPLICABLE' and self.platform_monthly_cap is None:
                raise ValueError('An enabled platform cap needs an explicit amount.')
        return self


class AllocationInput(Contract):
    """Trusted source adapter input, not an HTTP request or payment instruction.

    price_amount is either gross before discount or already discounted according
    to the explicit policy. Payment total includes separately evidenced tax.
    """
    model_config = ConfigDict(frozen=True)
    category: Literal['ATTENDED_BOOKING', 'NO_SHOW', 'SINGLE_GYM']
    price_amount: Money
    discount_amount: Money | None = None
    tax_amount: Money | None = None
    wallet_amount: Money
    gateway_amount: Money
    # This is the actual fee attributable to this allocation unit, not a checkout
    # fee to repeat on every visitor. Source adapters must reserve fee shares once.
    actual_gateway_fee: Money | None = None
    fee_tax: Money | None = None
    fee_basis: Literal['INCLUDING_TAX', 'EXCLUDING_TAX', 'UNAVAILABLE'] = 'UNAVAILABLE'
    fee_evidence_reference: str | None = Field(None, min_length=1, max_length=200)


class AllocationResult(Contract):
    model_config = ConfigDict(frozen=True)
    category: Literal['ATTENDED_BOOKING', 'NO_SHOW', 'SINGLE_GYM']
    eligible_amount: Money
    customer_funded_amount: Money
    wallet_amount: Money
    gateway_amount: Money
    gym_gross_share: Money
    fitigo_gross_commission: Money
    gateway_fee: Money | None
    gym_gateway_fee_share: Money | None
    fitigo_gateway_fee_share: Money | None
    # Negative net entitlements are retained for review, never clamped to zero.
    gym_owner_net_entitlement: Decimal | None
    fitigo_net_commission: Decimal | None
    fee_status: Literal['VERIFIED', 'WALLET_ONLY_NO_GATEWAY_FEE', 'PENDING_EVIDENCE']
    payout_readiness: Literal['NET_VALIDATED', 'FEE_PENDING', 'PROVISIONAL_GROSS', 'NEGATIVE_NET_REVIEW']
    entitlement_timing: Literal['UPFRONT', 'CONFIGURED_SETTLEMENT_CYCLE']
    statutory_reporting_enabled: Literal[False] = False