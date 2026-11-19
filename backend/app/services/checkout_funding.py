"""All amounts are Decimal; caller owns the user lock and transaction."""
from datetime import datetime, timedelta
from decimal import Decimal
from weakref import WeakKeyDictionary
from sqlalchemy import inspect, select
from fastapi import HTTPException
from app.models.checkout_funding import CheckoutFunding, BookingFunding
from app.models.wallet import WalletAccount, WalletTransaction
from app.models.booking import Booking
from app.core.config import settings

_schema = WeakKeyDictionary()
ZERO = Decimal('0.00')


def available(db):
    engine = db.get_bind()
    if engine not in _schema:
        inspector = inspect(db.connection())
        _schema[engine] = all(inspector.has_table(name) for name in ('checkout_funding', 'booking_funding'))
    return _schema[engine]


def get(db, checkout):
    return db.get(CheckoutFunding, checkout.id) if available(db) else None


def purchase_total(db, checkout):
    funding = get(db, checkout)
    return funding.total_amount if funding else Decimal(str(checkout.amount))


def has_wallet_contribution(db, checkout):
    funding = get(db, checkout)
    return bool(funding and funding.wallet_amount > 0)


def wallet_state(db, user_id, mode=None, lock=False):
    query = select(WalletAccount).where(WalletAccount.user_id == user_id)
    account = db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
    balance = Decimal(str(account.balance)) if account else ZERO
    hold_query = select(CheckoutFunding).where(CheckoutFunding.user_id == user_id, CheckoutFunding.state == 'HELD')
    holds = list(db.scalars(hold_query.with_for_update().execution_options(populate_existing=True) if lock else hold_query)) if available(db) else []
    held = sum((row.wallet_amount for row in holds), ZERO)
    eligible = max(ZERO, balance - held)
    reason = None
    from app.models.payment_checkout import PaymentCheckout
    refund_review = db.scalar(select(PaymentCheckout.id).where(PaymentCheckout.user_id == user_id,
        PaymentCheckout.failure_code == 'WALLET_REFUND_RECONCILIATION').limit(1))
    if refund_review: reason = 'Wallet recharge refund requires reconciliation. Contact support before spending.'
    elif not available(db): reason = 'Wallet spending requires the funding migration.'
    elif account and account.currency != 'INR': reason = 'Wallet currency does not match INR.'
    elif account and account.payment_mode and account.payment_mode != (mode or settings.gateway_mode): reason = 'Wallet belongs to a different payment environment.'
    elif account and not account.payment_mode and balance > 0 and (mode or settings.gateway_mode) == 'live': reason = 'Legacy wallet funds require reconciliation before live spending.'
    elif eligible <= 0: reason = 'No available wallet balance. Funds may be reserved by another checkout.'
    return account, dict(wallet_balance=str(balance), reserved_balance=str(held), available_wallet_balance=str(ZERO if reason else eligible), wallet_unavailable_reason=reason)


def preference(payload):
    return 'OFF' if not payload.use_wallet else 'MAX' if payload.wallet_amount is None else str(payload.wallet_amount.quantize(Decimal('.01')))


def calculate(db, user_id, total, payload):
    from app.services.payment_provider import minor
    total = Decimal(minor(total)) / 100
    _, state = wallet_state(db, user_id, lock=True)
    wanted = total if payload.wallet_amount is None else payload.wallet_amount
    amount = min(wanted, Decimal(state['available_wallet_balance']), total) if payload.use_wallet else ZERO
    if payload.use_wallet and payload.kind == 'WALLET_TOPUP': raise HTTPException(400, 'Wallet cannot fund a recharge.')
    if payload.use_wallet and state['wallet_unavailable_reason'] and Decimal(state['wallet_balance']) > 0 and 'No available' not in state['wallet_unavailable_reason']:
        raise HTTPException(409, state['wallet_unavailable_reason'])
    gateway = total - amount
    # Avoid silently charging a different remainder to satisfy provider minima.
    if gateway > 0 and gateway < 1:
        raise HTTPException(409, 'Online payment must be at least INR 1. Use the full wallet amount or reduce the wallet contribution.')
    return {**state, 'total_amount': str(total), 'wallet_amount': str(amount), 'gateway_amount': str(gateway),
            'currency': 'INR', 'provider': settings.gateway_name, 'mode': settings.gateway_mode}


def reserve(db, checkout, payload):
    if payload is None or not payload.use_wallet:
        if checkout.kind == 'WALLET_TOPUP': return
        if not available(db):
            if settings.source_evidence_enabled: raise HTTPException(409, 'Purchase funding migration is required.')
            return
        if get(db, checkout): return
        total = Decimal(str(checkout.amount))
        db.add(CheckoutFunding(checkout_id=checkout.id, user_id=checkout.user_id, total_amount=total,
            wallet_amount=ZERO, gateway_amount=total, mode=checkout.mode, currency=checkout.currency,
            state='NONE', request_wallet='OFF', expires_at=datetime.utcnow()+timedelta(minutes=15)))
        db.flush()
        for booking in db.scalars(select(Booking).where(Booking.checkout_id == checkout.id).order_by(Booking.id)):
            db.add(BookingFunding(booking_id=booking.id, checkout_id=checkout.id, total_amount=booking.total_price,
                wallet_amount=ZERO, gateway_amount=booking.total_price))
        checkout.snapshot = {**checkout.snapshot, 'funding_version': 1}
        db.flush()
        return
    if not available(db): raise HTTPException(409, 'Wallet spending requires the funding migration.')
    account, state = wallet_state(db, checkout.user_id, checkout.mode, lock=True)
    if state['wallet_unavailable_reason'] and 'reconciliation' in state['wallet_unavailable_reason']:
        raise HTTPException(409, state['wallet_unavailable_reason'])
    amounts = calculate(db, checkout.user_id, checkout.amount, payload)
    wallet = Decimal(amounts['wallet_amount']); total = Decimal(amounts['total_amount'])
    funding = CheckoutFunding(checkout_id=checkout.id, user_id=checkout.user_id, total_amount=total,
        wallet_amount=wallet, gateway_amount=total-wallet, mode=checkout.mode, currency=checkout.currency,
        state='HELD' if wallet else 'NONE', request_wallet=preference(payload), expires_at=datetime.utcnow()+timedelta(minutes=15))
    db.add(funding); db.flush()
    if wallet and account and not account.payment_mode: account.payment_mode = checkout.mode
    remaining = wallet
    # Deterministic oldest-ID-first allocation in paise; exact sums, no floating rounding.
    for booking in db.scalars(select(Booking).where(Booking.checkout_id == checkout.id).order_by(Booking.id)):
        price = Decimal(str(booking.total_price)); applied = min(remaining, price); remaining -= applied
        db.add(BookingFunding(booking_id=booking.id, checkout_id=checkout.id, total_amount=price,
            wallet_amount=applied, gateway_amount=price-applied))
    checkout.amount = funding.gateway_amount  # Existing adapters always charge this amount only.
    checkout.snapshot = {**checkout.snapshot, 'funding_version': 1}
    db.flush()


def validate_retry(db, checkout, payload):
    funding = get(db, checkout)
    if (funding.request_wallet if funding else 'OFF') != preference(payload):
        raise HTTPException(409, 'This checkout already has a fixed funding selection. Resume it or safely cancel it before changing payment methods.')


def debit(db, checkout):
    funding = get(db, checkout)
    if not funding or not funding.wallet_amount: return None
    if funding.state == 'DEBITED': return db.get(WalletTransaction, funding.wallet_transaction_id)
    if funding.state != 'HELD': raise HTTPException(409, 'Wallet reservation is no longer available. Payment needs review; do not pay again.')
    account, state = wallet_state(db, checkout.user_id, checkout.mode, lock=True)
    if state['wallet_unavailable_reason'] and 'reconciliation' in state['wallet_unavailable_reason']:
        raise HTTPException(409, state['wallet_unavailable_reason'])
    if not account or account.currency != checkout.currency or account.payment_mode != checkout.mode or Decimal(str(account.balance)) < funding.wallet_amount:
        raise HTTPException(409, 'Reserved wallet funds cannot be debited. Payment needs review.')
    existing = db.scalar(select(WalletTransaction).where(WalletTransaction.checkout_id == checkout.id))
    if existing: raise HTTPException(409, 'Wallet debit state requires reconciliation.')
    account.balance = Decimal(str(account.balance)) - funding.wallet_amount
    tx = WalletTransaction(account_id=account.id, user_id=checkout.user_id, direction='OUT', txn_type='PAYMENT',
        amount=funding.wallet_amount, currency=checkout.currency, checkout_id=checkout.id,
        reference=f'checkout:{checkout.id}', description=f'Wallet payment for {checkout.kind.lower().replace("_", " ")}')
    db.add(tx); db.flush()
    funding.state, funding.wallet_transaction_id, funding.resolved_at = 'DEBITED', tx.id, datetime.utcnow()
    return tx


def release(db, checkout):
    if not available(db): return
    # Caller holds the customer/checkout locks. Refresh the funding row under
    # lock too; release and checkout closure commit in the same transaction.
    funding = db.scalar(select(CheckoutFunding).where(CheckoutFunding.checkout_id == checkout.id)
        .with_for_update().execution_options(populate_existing=True))
    if not funding or funding.state != 'HELD': return
    from app.models.payment_checkout import PaymentAttempt
    conflict = db.scalar(select(PaymentAttempt.id).where(PaymentAttempt.checkout_id == checkout.id,
        (PaymentAttempt.status != 'FAILED') | (PaymentAttempt.refunded_amount > 0)).limit(1))
    if (checkout.status != 'CANCELLED' or not (checkout.checkout_data or {}).get('replacement_safe')
            or (checkout.checkout_data or {}).get('payment_processing') or conflict):
        raise HTTPException(409, 'Wallet reservation requires verified unpaid closure. Contact support.')
    funding.state, funding.resolved_at = 'RELEASED', datetime.utcnow()


def breakdown(db, checkout):
    funding = get(db, checkout)
    return dict(total_amount=str(funding.total_amount if funding else checkout.amount),
        wallet_amount=str(funding.wallet_amount if funding else ZERO), gateway_amount=str(checkout.amount),
        wallet_status=funding.state if funding else 'NONE', wallet_transaction_id=funding.wallet_transaction_id if funding else None,
        wallet_hold_expires_at=funding.expires_at.isoformat()+'Z' if funding and funding.state == 'HELD' else None)


def booking_breakdown(db, booking):
    if not available(db): return None
    allocation = db.get(BookingFunding, booking.id)
    if not allocation: return None
    return {'purchase_amount': str(allocation.total_amount), 'wallet_amount': str(allocation.wallet_amount),
        'gateway_amount': str(allocation.gateway_amount)}