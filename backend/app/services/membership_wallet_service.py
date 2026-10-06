"""Development-only test-credit checkout. All writes are one caller-owned transaction."""
import calendar
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.auth import User
from app.models.gym import Gym
from app.models.membership import GymMembershipPlan, UserMembership
from app.models.wallet import WalletAccount, WalletTransaction
from app.services.membership_entitlement import active_memberships


def wallet_enabled() -> bool:
    return settings.environment == "development"


def fail(code: str, status: int = 409):
    raise HTTPException(status_code=status, detail={"code": code})


def quote_key(terms: dict) -> str:
    # Capability flags are not purchased terms; do not affect acceptance.
    values = {k: v for k, v in terms.items() if k not in {"purchase_available", "wallet_checkout_available"}}
    return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def expiry(start: datetime, value: int, unit: str) -> datetime:
    if unit == "DAY":
        return start + timedelta(days=value)
    months = value * (12 if unit == "YEAR" else 1)
    target = start.year * 12 + start.month - 1 + months
    year, month = divmod(target, 12)
    if year > 9999:
        fail("PLAN_UNAVAILABLE")
    return start.replace(year=year, month=month+1, day=min(start.day, calendar.monthrange(year, month+1)[1]))


def lock_customer(db: Session, user_id: int):
    if not wallet_enabled():
        fail("WALLET_MVP_DISABLED", 403)
    user = db.scalars(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True)).first()
    if not user or user.status != "ACTIVE":
        fail("ACCOUNT_UNAVAILABLE", 403)


def activate(db: Session, *, user_id: int, terms: dict, checkout_key: str) -> UserMembership:
    # MySQL DATETIME columns have second precision. Rounding a fractional start
    # into the next second can make a just-purchased membership look future-dated
    # to a competing purchase despite the customer lock.
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    multi = terms["membership_type"] == "MULTI_GYM"
    # Caller holds the customer lock; competing purchases/QR scans share that lock.
    current = active_memberships(db, user_id, now, lock=True, include_paused=True)
    if any(multi or m.membership_type == "MULTI_GYM" or m.gym_id == terms["gym_id"] for m in current):
        fail("MEMBERSHIP_ALREADY_ACTIVE")
    if multi and not db.scalar(select(Gym.id).where(Gym.multi_gym_enabled.is_(True), Gym.status == "APPROVED", Gym.is_active.is_(True)).limit(1).with_for_update()):
        fail("NO_ELIGIBLE_PARTNER_GYMS")
    end = expiry(now, terms["duration_value"], terms["duration_unit"])
    amount = Decimal(terms["final_price"])
    account = db.scalars(select(WalletAccount).where(WalletAccount.user_id == user_id).with_for_update().execution_options(populate_existing=True)).first()
    if not account:
        fail("INSUFFICIENT_WALLET_BALANCE")
    if account.currency != terms["currency"]:
        fail("WALLET_CURRENCY_MISMATCH")
    if Decimal(account.balance) < amount:
        fail("INSUFFICIENT_WALLET_BALANCE")
    account.balance = Decimal(account.balance) - amount
    transaction = WalletTransaction(
        account_id=account.id, user_id=user_id, direction="OUT", txn_type="PAYMENT",
        amount=amount, currency=account.currency, reference=f"MEMBERSHIP:{checkout_key}",
        description=f"Test-credit membership purchase: {terms['name']}",
    )
    db.add(transaction)
    db.flush()
    membership = UserMembership(
        user_id=user_id, gym_id=None if multi else terms["gym_id"], plan_id=None if multi else terms["id"],
        platform_plan_id=terms["id"] if multi else None, membership_type=terms["membership_type"],
        checkout_key=checkout_key, wallet_transaction_id=transaction.id, terms_snapshot=terms,
        status="ACTIVE", start_at=now, end_at=end, original_end_at=end, paid_amount=amount, currency=terms["currency"],
        payment_provider="WALLET", payment_status="PAID", external_ref=f"WALLET_TXN:{transaction.id}",
    )
    db.add(membership)
    db.flush()
    return membership


def single_terms(db: Session, gym_id: int, plan_id: int, *, lock: bool = False) -> dict:
    query = select(GymMembershipPlan).where(GymMembershipPlan.id == plan_id, GymMembershipPlan.gym_id == gym_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    plan = db.scalars(query).first()
    gym_query = select(Gym).where(Gym.id == gym_id)
    if lock:
        gym_query = gym_query.with_for_update().execution_options(populate_existing=True)
    gym = db.scalars(gym_query).first()
    if not plan or not plan.is_active or not gym or gym.status != "APPROVED" or not gym.is_active:
        fail("PLAN_UNAVAILABLE", 404)
    return dict(id=plan.id, gym_id=gym_id, membership_type="SINGLE_GYM", name=plan.name,
                description=plan.description, duration_value=plan.duration_days, duration_unit="DAY",
                final_price=str(Decimal(plan.price).quantize(Decimal("0.01"))), currency=plan.currency,
                pause_rule={"allowed": bool(plan.pause_allowed), "max_pause_days": plan.max_pause_days or 0})


def buy_single(db: Session, *, user_id: int, gym_id: int, plan_id: int, accepted_quote: str, key: str) -> UserMembership:
    try:
        lock_customer(db, user_id)
        checkout_key = f"single:{key}"
        previous = db.scalars(select(UserMembership).where(UserMembership.user_id == user_id, UserMembership.checkout_key == checkout_key).with_for_update()).first()
        if previous:
            if previous.plan_id != plan_id or previous.gym_id != gym_id:
                fail("IDEMPOTENCY_CONFLICT")
            db.commit()
            return previous
        terms = single_terms(db, gym_id, plan_id, lock=True)
        if quote_key(terms) != accepted_quote:
            fail("MEMBERSHIP_PRICE_CHANGED")
        result = activate(db, user_id=user_id, terms=terms, checkout_key=checkout_key)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise