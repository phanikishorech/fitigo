"""Provider-neutral contracts. No booking/membership rules belong in adapters."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol

from fastapi import HTTPException


def minor(amount) -> int:
    try:
        value = Decimal(str(amount)) * 100
        if not value.is_finite() or value < 0 or value != value.to_integral_value():
            raise ValueError()
        return int(value)
    except (ValueError, ArithmeticError):
        raise HTTPException(409, detail="Invalid payment amount") from None


@dataclass
class ProviderOrder:
    id: str
    reference: str
    amount: int
    currency: str
    paid: bool
    payable: bool = True
    checkout_data: dict = field(default_factory=dict)


@dataclass
class ProviderRefund:
    id: str
    payment_id: str
    amount: int
    currency: str
    status: str
    occurred_at: datetime | None = None
    timestamp_source: str = 'UNAVAILABLE'


def provider_time(value):
    """Only timezone-explicit provider timestamps; no guessed local timezone."""
    try:
        if isinstance(value, str):
            at = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return at.astimezone(timezone.utc) if at.tzinfo else None
    except (ValueError, OverflowError):
        pass
    return None


@dataclass
class ProviderPayment:
    id: str
    order_id: str
    amount: int
    currency: str
    status: str  # SUCCESS, PENDING, FAILED
    refunded: int = 0
    collection_state: str | None = None
    captured_at: datetime | None = None
    timestamp_source: str = 'UNAVAILABLE'
    fee: int | None = None
    fee_tax: int | None = None
    fee_basis: str = 'UNAVAILABLE'
    refunds: list[ProviderRefund] = field(default_factory=list)
    refund_evidence_status: str = 'UNAVAILABLE'


@dataclass
class ProviderEvent:
    name: str
    order_id: str
    reference: str | None = None


class PaymentProvider(Protocol):
    name: str
    key_id: str

    def validate_customer(self, customer) -> None: ...
    def validate_purchase(self, checkout, customer) -> None: ...
    def create_order(self, checkout, customer) -> ProviderOrder: ...
    def find_order(self, reference: str) -> ProviderOrder | None: ...
    def order(self, order_id: str) -> ProviderOrder: ...
    def terminate_order(self, order_id: str) -> ProviderOrder: ...
    def payments(self, order_id: str, payment_id: str | None = None) -> list[ProviderPayment]: ...
    def verify_confirmation(self, checkout, payment_id, signature, order_id) -> None: ...
    def webhook(self, raw: bytes, signature: str, timestamp: str) -> ProviderEvent | None: ...
    def checkout_info(self, checkout) -> dict: ...


def check_order(checkout, order: ProviderOrder):
    if (order.reference != checkout.id or order.amount != minor(checkout.amount)
            or order.currency != checkout.currency or not order.id
            or (checkout.gateway_order_id and order.id != checkout.gateway_order_id)):
        raise HTTPException(409, detail="Gateway order does not match checkout")