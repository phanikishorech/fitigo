"""Wrap the existing Razorpay transport without changing its signing contract."""
import json
import re
from fastapi import HTTPException
from app.core.config import settings
from app.services.razorpay_gateway import RazorpayGateway, verify_signature
from app.services.payment_provider import ProviderOrder, ProviderPayment, ProviderEvent


class RazorpayProvider:
    name = "RAZORPAY"

    def __init__(self, gateway=None):
        self.gateway = gateway if gateway is not None else RazorpayGateway()
        self.key_id = settings.razorpay_key_id

    def validate_customer(self, customer):
        pass

    def validate_purchase(self, checkout, customer):
        self.validate_customer(customer)

    def normalize_order(self, row):
        if not isinstance(row, dict) or not re.fullmatch(r"order_[A-Za-z0-9]+", row.get("id", "")):
            raise HTTPException(409, detail="Invalid gateway order")
        return ProviderOrder(row["id"], row.get("receipt"), row.get("amount"), row.get("currency"),
            row.get("status") == "paid" and row.get("amount_paid") == row.get("amount") and row.get("amount_due") == 0,
            row.get("status") != "paid")

    def create_order(self, checkout, customer):
        return self.normalize_order(self.gateway.create_order(checkout))

    def find_order(self, reference):
        row = self.gateway.find_order(reference)
        return self.normalize_order(row) if row else None

    def order(self, order_id):
        return self.normalize_order(self.gateway.order(order_id))

    def payments(self, order_id, payment_id=None):
        rows = ([self.gateway.payment(payment_id)] if payment_id else []) + self.gateway.payments(order_id)
        result = []
        for row in rows:
            if not isinstance(row, dict) or not re.fullmatch(r"pay_[A-Za-z0-9]+", row.get("id", "")):
                raise HTTPException(409, detail="Invalid gateway payment")
            row = self.gateway.payment(row["id"])
            state = "SUCCESS" if row.get("status") == "captured" and row.get("captured") is True else "PENDING" if row.get("status") in {"authorized", "created"} else "FAILED"
            result.append(ProviderPayment(row["id"], row.get("order_id"), row.get("amount"), row.get("currency"), state,
                row.get("amount_refunded", 0)))
        return result

    def verify_confirmation(self, checkout, payment_id, signature, order_id):
        if any(value is not None for value in (payment_id, signature, order_id)):
            if not all((payment_id, signature, order_id)) or checkout.gateway_order_id != order_id:
                raise HTTPException(400, detail="Payment order mismatch")
            verify_signature(f"{checkout.gateway_order_id}|{payment_id}".encode(), signature, settings.razorpay_key_secret.get_secret_value())

    def webhook(self, raw, signature, timestamp=""):
        verify_signature(raw, signature, settings.razorpay_webhook_secret.get_secret_value())
        try:
            event = json.loads(raw)
            name = event.get("event", "")
            if name not in {"payment.captured", "payment.authorized", "payment.failed", "order.paid", "refund.processed"}:
                return None
            payload = event.get("payload", {})
            payment = payload.get("payment", {}).get("entity", {})
            order_id = payment.get("order_id") or payload.get("order", {}).get("entity", {}).get("id")
            if not order_id and name == "refund.processed":
                payment_id = payload.get("refund", {}).get("entity", {}).get("payment_id", "")
                if not re.fullmatch(r"pay_[A-Za-z0-9]+", payment_id):
                    raise ValueError()
                order_id = self.gateway.payment(payment_id).get("order_id")
            if not isinstance(order_id, str) or not re.fullmatch(r"order_[A-Za-z0-9]+", order_id):
                raise ValueError()
            return ProviderEvent(name, order_id, (payment.get("notes") or {}).get("fitigo_checkout_id"))
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(400, detail="Invalid webhook payload") from None

    def checkout_info(self, checkout):
        return {"key_id": checkout.key_id, "razorpay_order_id": checkout.gateway_order_id}