"""Wrap the existing Razorpay transport without changing its signing contract."""
import json
import re
from fastapi import HTTPException
from app.core.config import settings
from app.services.razorpay_gateway import RazorpayGateway, verify_signature
from app.services.payment_provider import ProviderOrder, ProviderPayment, ProviderEvent, ProviderRefund


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
        if row.get('status') not in {'created', 'attempted', 'paid'}:
            raise HTTPException(409, detail="Unrecognized gateway order status. Refresh payment status.")
        return ProviderOrder(row["id"], row.get("receipt"), row.get("amount"), row.get("currency"),
            row.get("status") == "paid" and row.get("amount_paid") == row.get("amount") and row.get("amount_due") == 0,
            row.get("status") != "paid", {
                'unpaid_verified': row.get('status') in {'created', 'attempted'} and row.get('amount_paid') == 0
                    and row.get('amount_due') == row.get('amount'),
                'expected_attempts': row.get('attempts')})

    def create_order(self, checkout, customer):
        return self.normalize_order(self.gateway.create_order(checkout))

    def find_order(self, reference):
        row = self.gateway.find_order(reference)
        return self.normalize_order(row) if row else None

    def order(self, order_id):
        return self.normalize_order(self.gateway.order(order_id))

    def terminate_order(self, order_id):
        raise HTTPException(409, detail="This gateway cannot safely close the previous order automatically. Resolve it through payment history or support before starting another payment.")

    def payments(self, order_id, payment_id=None):
        rows = ([self.gateway.payment(payment_id)] if payment_id else []) + self.gateway.payments(order_id)
        result = []
        for row in rows:
            if not isinstance(row, dict) or not re.fullmatch(r"pay_[A-Za-z0-9]+", row.get("id", "")):
                raise HTTPException(409, detail="Invalid gateway payment")
            row = self.gateway.payment(row["id"])
            if row.get('status') not in {'created', 'authorized', 'captured', 'refunded', 'failed'}:
                raise HTTPException(409, detail="Unrecognized gateway payment status. Refresh payment status.")
            state = "SUCCESS" if row.get("status") in {"captured", "refunded"} and row.get("captured") is True else "FAILED" if row.get('status') == 'failed' else "PENDING"
            payment = ProviderPayment(row["id"], row.get("order_id"), row.get("amount"), row.get("currency"), state,
                row.get("amount_refunded", 0), collection_state='CAPTURED' if state == 'SUCCESS' else
                    'FAILED' if state == 'FAILED' else 'AUTHORIZED' if row['status']=='authorized' else 'INITIATED')
            # Payment created_at is NOT capture time. REST payment entity provides
            # no authoritative captured_at: retain null rather than fabricate it.
            payment.fee = row.get('fee') if type(row.get('fee')) is int and row['fee'] >= 0 else None
            payment.fee_tax = row.get('tax') if type(row.get('tax')) is int and row['tax'] >= 0 else None
            payment.fee_basis = 'INCLUDING_TAX' if payment.fee is not None else 'UNAVAILABLE'
            if settings.source_evidence_enabled and payment.refunded and hasattr(self.gateway, 'refunds'):
                for refund in self.gateway.refunds(payment.id):
                    if not isinstance(refund, dict) or not re.fullmatch(r'rfnd_[A-Za-z0-9]+', refund.get('id', '')) or refund.get('payment_id') != payment.id or refund.get('currency') != payment.currency or type(refund.get('amount')) is not int or refund['amount'] < 0:
                        raise HTTPException(409, 'Invalid provider refund evidence')
                    # Refund created_at is not a successful processing timestamp.
                    payment.refunds.append(ProviderRefund(refund['id'], payment.id, refund['amount'], payment.currency,
                        refund.get('status', 'UNKNOWN')))
                payment.refund_evidence_status = 'PROVIDER_FETCHED'
            result.append(payment)
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