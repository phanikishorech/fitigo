"""Bounded recovery for existing checkout holds; never release on browser close."""
from datetime import datetime
from sqlalchemy import select
from app.models.checkout_funding import CheckoutFunding
from app.services import checkout_funding as funding


def resolve(service, checkout_id, user_id):
    checkout = service.owned(checkout_id, user_id)
    hold = funding.get(service.db, checkout)
    if not hold or hold.state != 'HELD': return service.present(checkout)
    if checkout.status == 'CREATED' and not checkout.gateway_order_id:
        if hold.expires_at <= datetime.utcnow():
            service.close_unpaid(checkout); service.db.commit()
        return service.present(checkout)
    # Provider evidence is required even after local expiry. Unknown outcomes retain hold.
    result = service.reconcile(checkout.id, user_id)
    checkout = service.owned(checkout_id, user_id)
    if hold.state != 'HELD' or checkout.status in {'PAID', 'REVIEW_REQUIRED', 'REFUNDED'}: return result
    if hold.expires_at > datetime.utcnow() and checkout.status != 'FAILED': return result
    data = checkout.checkout_data or {}
    if data.get('payment_processing') or checkout.status == 'CREATING': return result
    if checkout.provider == 'CASHFREE' and checkout.gateway_order_id and not data.get('replacement_safe'):
        # Use the same durable cancellation intent and fresh evidence checks as
        # explicit cancellation. A lost PATCH response must not reopen payment.
        result = service.cancel(checkout.id, user_id)
        checkout = service.owned(checkout_id, user_id)
        data = checkout.checkout_data or {}
    if checkout.status in {'PAID', 'REVIEW_REQUIRED', 'REFUNDED'}: return result
    if data.get('replacement_safe'):
        service.close_unpaid(checkout)
        service.db.commit()
    elif checkout.provider == 'RAZORPAY' and hold.expires_at <= datetime.utcnow():
        # Failure is not unpaid order closure: late authorization or a new
        # attempt in an old browser window can still capture. Retain the hold.
        checkout.failure_code = 'WALLET_HOLD_REQUIRES_PROVIDER_CLOSURE'
        service.db.commit()
    return service.present(checkout)


def recover_due(db, limit=50):
    from app.services.payment_checkout_service import PaymentCheckoutService
    if not funding.available(db): return {'checked': 0, 'unresolved': 0}
    from app.models.payment_checkout import PaymentCheckout
    rows = list(db.execute(select(CheckoutFunding.checkout_id, CheckoutFunding.user_id).join(
        PaymentCheckout, PaymentCheckout.id == CheckoutFunding.checkout_id).where(
        CheckoutFunding.state == 'HELD', CheckoutFunding.expires_at <= datetime.utcnow())
        .order_by(PaymentCheckout.updated_at, CheckoutFunding.expires_at).limit(limit)))
    db.rollback()
    unresolved = 0
    for checkout_id, user_id in rows:
        try:
            result = resolve(PaymentCheckoutService(db), checkout_id, user_id)
            if result.get('wallet_status') == 'HELD': unresolved += 1
        except Exception:
            db.rollback(); unresolved += 1
        finally:
            db.rollback()
            # Rotate unresolved holds so a bounded batch cannot starve newer holds.
            # Timestamp only; never infer failure from time or mutate funding amounts.
            from sqlalchemy import update
            db.execute(update(PaymentCheckout).where(PaymentCheckout.id == checkout_id).values(updated_at=datetime.utcnow()))
            db.commit()
    return {'checked': len(rows), 'unresolved': unresolved}


async def recovery_loop(stop):
    """Independent transactions; multiple API workers serialize on customer locks."""
    import asyncio
    import logging
    from starlette.concurrency import run_in_threadpool
    from app.database.session import SessionLocal
    def tick():
        if SessionLocal is None: return
        with SessionLocal() as db: return recover_due(db)
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except asyncio.TimeoutError:
            try: await run_in_threadpool(tick)
            except Exception: logging.getLogger(__name__).warning('Wallet hold recovery failed; pending funds retained.')