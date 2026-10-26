"""Razorpay REST transport using the project's existing httpx dependency."""
import hashlib
import hmac
import re

import httpx
from fastapi import HTTPException
from app.core.config import settings
from app.services.payment_provider import minor


def configured() -> bool:
    prefix = f"rzp_{settings.gateway_mode}_"
    return bool((settings.razorpay_enabled or settings.payment_gateway is not None) and settings.razorpay_key_id.startswith(prefix)
                and settings.razorpay_key_secret.get_secret_value() and settings.razorpay_webhook_secret.get_secret_value()
                and (settings.gateway_mode == "test" or (settings.razorpay_live_enabled and settings.environment == "production")))


def require_gateway():
    if not configured():
        raise HTTPException(503, detail="Razorpay payments are not configured for the selected mode")


def verify_signature(body: bytes, signature: str, secret: str):
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not secret or not re.fullmatch(r"[a-fA-F0-9]{64}", signature or "") or not hmac.compare_digest(expected, signature.lower()):
        raise HTTPException(400, detail="Invalid payment signature")


class RazorpayGateway:
    def request(self, method: str, path: str, **kwargs) -> dict:
        require_gateway()
        try:
            with httpx.Client(base_url="https://api.razorpay.com/v1/", timeout=15.0,
                              auth=(settings.razorpay_key_id, settings.razorpay_key_secret.get_secret_value())) as client:
                response = client.request(method, path, **kwargs)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("Invalid gateway response")
                return data
        except (httpx.HTTPError, ValueError):
            # Never return provider payloads, authorization headers, or secrets.
            raise HTTPException(503, detail="Payment provider unavailable. Refresh payment status before retrying.") from None

    def create_order(self, checkout):
        return self.request("POST", "orders", json={"amount": minor(checkout.amount), "currency": checkout.currency,
            "receipt": checkout.id, "partial_payment": False, "notes": {"fitigo_checkout_id": checkout.id}})

    def find_order(self, receipt):
        rows = self.request("GET", "orders", params={"receipt": receipt, "count": 100}).get("items", [])
        matches = [row for row in rows if row.get("receipt") == receipt]
        if len(matches) > 1:
            raise HTTPException(409, detail="Payment order needs manual reconciliation")
        return matches[0] if matches else None

    def order(self, order_id):
        return self.request("GET", f"orders/{order_id}")

    def payment(self, payment_id):
        return self.request("GET", f"payments/{payment_id}")

    def payments(self, order_id):
        return self.request("GET", f"orders/{order_id}/payments").get("items", [])