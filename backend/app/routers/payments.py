from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, Query
from typing import Literal
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from app.core.config import settings
from app.core.dependencies import require_role
from app.core.roles import ROLE_CUSTOMER
from app.database.session import get_db
from app.models.auth import User
from app.models.payment_checkout import PaymentCheckout
from app.schemas.payment_checkout import CheckoutCreate, CheckoutVerify
from app.services.payment_checkout_service import PaymentCheckoutService
from app.services.payment_providers import configured


def no_store(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/payments", dependencies=[Depends(no_store)])
customer = require_role({ROLE_CUSTOMER})


@router.get('/history')
def payment_history(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                    status: str | None = Query(None, max_length=30),
                    kind: Literal['BOOKING', 'CART', 'SINGLE_GYM', 'MULTI_GYM', 'WALLET_TOPUP', 'WALLET_LEDGER'] | None = None,
                    db: Session = Depends(get_db), user: User = Depends(customer)):
    from app.services.customer_payment_history import history
    return history(db, user.id, limit, offset, status, kind)


@router.get("/config")
def configuration(user: User = Depends(customer)):
    return {"enabled": configured(), "gateway_required": settings.gateway_required, "mode": settings.gateway_mode,
            "environment": settings.gateway_environment, "provider": settings.gateway_name}


@router.post("/checkouts")
def create_checkout(payload: CheckoutCreate,
                    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"),
                    db: Session = Depends(get_db), user: User = Depends(customer)):
    return PaymentCheckoutService(db).create(user.id, payload, idempotency_key)


@router.get("/checkouts")
def recent_checkouts(db: Session = Depends(get_db), user: User = Depends(customer)):
    service = PaymentCheckoutService(db)
    return [service.present(row) for row in db.scalars(select(PaymentCheckout).where(
        PaymentCheckout.user_id == user.id, PaymentCheckout.mode == settings.gateway_mode
        ).order_by(PaymentCheckout.created_at.desc()).limit(20))]


@router.get("/checkouts/{checkout_id}")
def checkout_status(checkout_id: UUID, db: Session = Depends(get_db), user: User = Depends(customer)):
    service = PaymentCheckoutService(db)
    return service.present(service.owned(str(checkout_id), user.id))


@router.post("/checkouts/{checkout_id}/verify")
def verify_checkout(checkout_id: UUID, payload: CheckoutVerify, db: Session = Depends(get_db), user: User = Depends(customer)):
    return PaymentCheckoutService(db).reconcile(str(checkout_id), user.id, payload.razorpay_payment_id,
                                               payload.razorpay_signature, payload.razorpay_order_id)


@router.post("/checkouts/{checkout_id}/refresh")
def refresh_checkout(checkout_id: UUID, db: Session = Depends(get_db), user: User = Depends(customer)):
    return PaymentCheckoutService(db).start(str(checkout_id), user.id)


@router.post("/checkouts/{checkout_id}/cancel")
def cancel_checkout(checkout_id: UUID, db: Session = Depends(get_db), user: User = Depends(customer)):
    return PaymentCheckoutService(db).cancel(str(checkout_id), user.id)


@router.post("/webhooks/razorpay")
async def webhook(request: Request, x_razorpay_signature: str = Header(default=""),
                  x_razorpay_event_id: str = Header(..., min_length=1, max_length=100), db: Session = Depends(get_db)):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 262144:
            raise HTTPException(413, detail="Webhook body too large")
    return await run_in_threadpool(PaymentCheckoutService(db).webhook, bytes(raw), x_razorpay_signature, x_razorpay_event_id)


@router.post("/webhooks/cashfree")
async def cashfree_webhook(request: Request, x_webhook_signature: str = Header(default="", max_length=128),
                          x_webhook_timestamp: str = Header(default="", max_length=32), db: Session = Depends(get_db)):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 262144:
            raise HTTPException(413, detail="Webhook body too large")
    return await run_in_threadpool(PaymentCheckoutService(db).webhook, bytes(raw), x_webhook_signature,
                                  "", "CASHFREE", x_webhook_timestamp)