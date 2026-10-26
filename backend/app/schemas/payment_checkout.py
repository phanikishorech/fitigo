from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class CheckoutCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["CART", "BOOKING", "SINGLE_GYM", "MULTI_GYM"]
    booking_id: int | None = Field(default=None, gt=0)
    gym_id: int | None = Field(default=None, gt=0)
    plan_id: int | None = Field(default=None, gt=0)
    order_id: str | None = Field(default=None, max_length=36)
    accepted_quote: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def source(self):
        required = {"CART": [], "BOOKING": ["booking_id"], "SINGLE_GYM": ["gym_id", "plan_id", "accepted_quote"], "MULTI_GYM": ["order_id", "accepted_quote"]}[self.kind]
        if any(getattr(self, name) is None for name in required):
            raise ValueError("Missing checkout source fields")
        if any(getattr(self, name) is not None for name in {"booking_id", "gym_id", "plan_id", "order_id", "accepted_quote"} - set(required)):
            raise ValueError("Unexpected checkout source fields")
        return self


class CheckoutVerify(BaseModel):
    model_config = ConfigDict(extra="forbid")
    razorpay_order_id: str | None = Field(default=None, pattern=r"^order_[A-Za-z0-9]{1,64}$")
    razorpay_payment_id: str | None = Field(default=None, pattern=r"^pay_[A-Za-z0-9]{1,64}$")
    razorpay_signature: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")

    @model_validator(mode="after")
    def complete_callback(self):
        fields = (self.razorpay_order_id, self.razorpay_payment_id, self.razorpay_signature)
        if any(fields) and not all(fields):
            raise ValueError("Provide the complete Razorpay callback or an empty confirmation request")
        return self