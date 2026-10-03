from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2, allow_inf_nan=False)]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PlatformPlanCreate(StrictRequest):
    code: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]+$")
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    duration_value: int = Field(ge=1, le=3660)
    duration_unit: Literal["DAY", "MONTH", "YEAR"]
    base_price: Money
    # INR is the only configured currency in this foundation. Never guess FX or minor units.
    currency: Literal["INR"]
    benefits: list[Annotated[str, Field(min_length=1, max_length=250)]] = Field(default_factory=list, max_length=20)
    badge: str | None = Field(default=None, min_length=1, max_length=60)
    display_order: int = Field(default=0, ge=0, le=100000)
    is_active: bool = False


class PlatformPlanUpdate(PlatformPlanCreate):
    expected_version: int = Field(ge=1)


class PlatformOfferUpdate(StrictRequest):
    expected_version: int = Field(ge=1)
    kind: Literal["PERCENTAGE", "FIXED"]
    value: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2, allow_inf_nan=False)]
    title: str | None = Field(default=None, min_length=1, max_length=120)
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    is_active: bool = False

    @model_validator(mode="after")
    def valid_offer(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("Offer end must follow its start")
        if self.kind == "PERCENTAGE" and self.value > 100:
            raise ValueError("Percentage cannot exceed 100")
        return self


class ActiveOffer(BaseModel):
    id: int
    kind: Literal["PERCENTAGE", "FIXED"]
    title: str | None
    valid_until: datetime


class AccessRule(BaseModel):
    scope: Literal["ELIGIBLE_PARTNER_GYMS"] = "ELIGIBLE_PARTNER_GYMS"
    daily_access: Literal[1] = 1


class PlatformPlanResponse(BaseModel):
    id: int
    code: str
    membership_type: Literal["MULTI_GYM"] = "MULTI_GYM"
    name: str
    description: str | None
    duration_value: int
    duration_unit: Literal["DAY", "MONTH", "YEAR"]
    base_price: Money
    final_price: Money
    discount_amount: Money
    discount_percentage: Decimal | None
    currency: str
    offer: ActiveOffer | None
    benefits: list[str]
    badge: str | None
    display_order: int
    is_active: bool
    version: int
    access_rule: AccessRule = Field(default_factory=AccessRule)
    pause_rule: None = None
    purchase_available: bool = False


class PlatformCatalogResponse(BaseModel):
    items: list[PlatformPlanResponse]
    server_time: datetime
    checkout_available: bool = False
    checkout_unavailable_reason: str | None = "PAYMENT_NOT_CONFIGURED"
    payment_mode: str = "DISABLED"


class PlatformOrderCreate(StrictRequest):
    plan_id: int = Field(gt=0, strict=True)


class AdminOfferConfiguration(BaseModel):
    id: int
    kind: Literal["PERCENTAGE", "FIXED"]
    value: Decimal
    title: str | None
    starts_at: datetime
    ends_at: datetime
    is_active: bool
    state: Literal["ACTIVE", "SCHEDULED", "EXPIRED", "DISABLED"]


class AdminPlanDetail(BaseModel):
    plan: PlatformPlanResponse
    offer_configuration: AdminOfferConfiguration | None
    server_time: datetime


class PlatformOrderResponse(BaseModel):
    id: str
    status: str = "PAYMENT_DISABLED"
    payment_status: str = "NOT_STARTED"
    eligibility_status: str = "NOT_EVALUATED"
    plan: PlatformPlanResponse
    created_at: datetime
    current_plan: PlatformPlanResponse | None
    requires_review: bool
    payment_available: bool = False
    membership_id: int | None = None
    quote_token: str | None = None
    payment_mode: str = "DISABLED"
    wallet_balance: str | None = None
    wallet_currency: str | None = None
    wallet_transaction_id: int | None = None


class WalletOrderPayment(StrictRequest):
    accepted_quote: str = Field(pattern=r"^[a-f0-9]{64}$")


class PartnerUpdate(StrictRequest):
    enabled: bool