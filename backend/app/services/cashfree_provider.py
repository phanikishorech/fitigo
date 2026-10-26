"""Cashfree PG REST API 2026-01-01 using the existing httpx dependency.

Only hosted checkout sessions reach the browser. Payment data is fetched from
Cashfree, never accepted from a browser or trusted solely from a webhook.
"""
import base64
import hashlib
import hmac
import json
import re
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException
from app.core.config import settings
from app.services.payment_provider import ProviderOrder, ProviderPayment, ProviderEvent, minor


class CashfreeProvider:
    name = "CASHFREE"

    def __init__(self):
        # Store an account fingerprint, not the client ID, in the shared key column.
        self.key_id = hashlib.sha256(settings.cashfree_client_id.encode()).hexdigest()
        self.base_url = "https://sandbox.cashfree.com/pg/" if settings.gateway_mode == "test" else "https://api.cashfree.com/pg/"

    def request(self, method, path, *, missing=False, **kwargs):
        from app.services.payment_providers import require_gateway
        require_gateway(self.name)
        headers = {"x-client-id": settings.cashfree_client_id,
            "x-client-secret": settings.cashfree_client_secret.get_secret_value(),
            "x-api-version": settings.cashfree_api_version, "Accept": "application/json"}
        headers.update(kwargs.pop("headers", {}))
        try:
            with httpx.Client(base_url=self.base_url, timeout=15.0, follow_redirects=False) as client:
                response = client.request(method, path, headers=headers, **kwargs)
                if missing and response.status_code == 404:
                    error = response.json()
                    if isinstance(error, dict) and error.get("type") == "invalid_request_error" and error.get("code") in {"order_not_found", "something_not_found"}:
                        return None
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, (dict, list)):
                    raise ValueError()
                return data
        except (httpx.HTTPError, ValueError):
            raise HTTPException(503, detail="Payment provider unavailable. Refresh payment status before retrying.") from None

    def probe_credentials(self):
        self.request("GET", f"orders/fitigo_probe_{uuid4().hex}", missing=True)

    def validate_customer(self, customer):
        phone = re.sub(r"[\s()-]", "", customer.phone or "")
        if not re.fullmatch(r"(?:\+?[1-9][0-9]{0,3})?[0-9]{10}", phone):
            raise HTTPException(409, detail="Add a valid phone number to your profile before using Cashfree checkout")

    @staticmethod
    def external_id(reference):
        return f"fitigo_{UUID(reference).hex}"

    def validate_purchase(self, checkout, customer):
        if minor(checkout.amount) == 0:
            return  # Existing free-plan fulfillment does not need a gateway session.
        self.validate_customer(customer)
        if minor(checkout.amount) < 100:
            raise HTTPException(409, detail="Cashfree requires a minimum payment of INR 1")

    def normalize_order(self, row):
        try:
            order_id = row["order_id"]
            if not isinstance(order_id, str) or not re.fullmatch(r"fitigo_[a-f0-9]{32}", order_id):
                raise ValueError()
            reference = str(UUID(hex=order_id.removeprefix("fitigo_")))
            state = row["order_status"]
            if state not in {"ACTIVE", "PAID", "EXPIRED", "TERMINATED", "TERMINATION_REQUESTED"}:
                raise ValueError()
            session = row.get("payment_session_id")
            if state == "ACTIVE" and (not isinstance(session, str) or not session):
                raise ValueError()
            return ProviderOrder(order_id, reference, minor(row["order_amount"]), row["order_currency"],
                state == "PAID", state == "ACTIVE", {"payment_session_id": session, "payable": state == "ACTIVE"})
        except (KeyError, ValueError, TypeError, AttributeError):
            raise HTTPException(409, detail="Invalid Cashfree order response") from None

    def create_order(self, checkout, customer):
        self.validate_purchase(checkout, customer)
        # JSON number is serialized from exact minor units; never frontend pricing.
        row = self.request("POST", "orders", headers={"x-idempotency-key": checkout.id}, json={
            "order_id": self.external_id(checkout.id), "order_amount": minor(checkout.amount) / 100,
            "order_currency": checkout.currency,
            "customer_details": {"customer_id": f"fitigo_user_{customer.id}",
                "customer_phone": re.sub(r"[\s()-]", "", customer.phone), "customer_email": customer.email},
            "order_meta": {"return_url": settings.payment_return_url},
            "order_tags": {"fitigo_checkout_id": checkout.id}})
        return self.normalize_order(row)

    def find_order(self, reference):
        row = self.request("GET", f"orders/{self.external_id(reference)}", missing=True)
        return self.normalize_order(row) if row is not None else None

    def order(self, order_id):
        return self.normalize_order(self.request("GET", f"orders/{order_id}"))

    def payments(self, order_id, payment_id=None):
        rows = self.request("GET", f"orders/{order_id}/payments")
        if not isinstance(rows, list):
            raise HTTPException(409, detail="Invalid Cashfree payment response")
        result = []
        for row in rows:
            try:
                identifier = str(row["cf_payment_id"])
                if not re.fullmatch(r"[0-9]{1,64}", identifier):
                    raise ValueError()
                state = row["payment_status"]
                if state not in {"SUCCESS", "PENDING", "NOT_ATTEMPTED", "FAILED", "USER_DROPPED", "VOID", "CANCELLED"}:
                    raise ValueError()
                if state in {"PENDING", "NOT_ATTEMPTED"} or (state == "SUCCESS" and row.get("is_captured") is False):
                    state = "PENDING"
                elif state != "SUCCESS":
                    state = "FAILED"
                result.append(ProviderPayment(identifier, row["order_id"], minor(row["payment_amount"]), row["payment_currency"], state))
            except (KeyError, ValueError, TypeError):
                raise HTTPException(409, detail="Invalid Cashfree payment response") from None
        # Preserve the existing dashboard-refund reconciliation capability.
        if any(p.status == "SUCCESS" for p in result):
            refunds = self.request("GET", f"orders/{order_id}/refunds")
            if not isinstance(refunds, list):
                raise HTTPException(409, detail="Invalid Cashfree refund response")
            seen = set()
            for row in refunds:
                if not isinstance(row, dict):
                    raise HTTPException(409, detail="Invalid Cashfree refund response")
                if row.get("refund_status") != "SUCCESS":
                    continue
                identifier = str(row.get("cf_refund_id", ""))
                payment = next((p for p in result if p.id == str(row.get("cf_payment_id"))), None)
                if not identifier or not payment or row.get("order_id") != order_id or row.get("refund_currency") != payment.currency:
                    raise HTTPException(409, detail="Cashfree refund does not match payment")
                if identifier not in seen:
                    payment.refunded += minor(row.get("refund_amount"))
                    seen.add(identifier)
        return result

    def verify_confirmation(self, checkout, payment_id, signature, order_id):
        if any(value is not None for value in (payment_id, signature, order_id)):
            raise HTTPException(400, detail="Cashfree confirmation accepts no browser payment assertions")

    def webhook(self, raw, signature, timestamp):
        secret = settings.cashfree_client_secret.get_secret_value()
        if not secret or not re.fullmatch(r"[0-9]{10,16}", timestamp or "") or not re.fullmatch(r"[A-Za-z0-9+/]{43}=", signature or ""):
            raise HTTPException(400, detail="Invalid payment signature")
        expected = base64.b64encode(hmac.new(secret.encode(), timestamp.encode() + raw, hashlib.sha256).digest()).decode()
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(400, detail="Invalid payment signature")
        try:
            event = json.loads(raw)
            name = event.get("type")
            if name not in {"PAYMENT_SUCCESS_WEBHOOK", "PAYMENT_FAILED_WEBHOOK", "PAYMENT_USER_DROPPED_WEBHOOK", "REFUND_STATUS_WEBHOOK"}:
                return None
            data = event["data"]
            order_id = data.get("order", {}).get("order_id") or data.get("refund", {}).get("order_id")
            if not isinstance(order_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{3,45}", order_id):
                raise ValueError()
            # Shared merchant accounts may send orders from other applications.
            if not re.fullmatch(r"fitigo_[a-f0-9]{32}", order_id):
                return None
            return ProviderEvent(name, order_id, str(UUID(hex=order_id.removeprefix("fitigo_"))))
        except (ValueError, KeyError, AttributeError, TypeError):
            raise HTTPException(400, detail="Invalid webhook payload") from None

    def checkout_info(self, checkout):
        return {"key_id": "", "razorpay_order_id": None,
            "payment_session_id": (checkout.checkout_data or {}).get("payment_session_id")}