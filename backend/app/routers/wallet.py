from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_optional_user
from app.database.session import get_db
from app.models.auth import User
from app.models.wallet import WalletAccount, WalletTransaction, WalletTxnDirection, WalletTxnType
from app.schemas.wallet import (
    WalletBalanceResponse,
    WalletTopupRequest,
    WalletTopupResponse,
    WalletTransactionResponse,
    WalletTransactionsResponse,
)


router = APIRouter(prefix="/wallet")


def _maybe_raise_migration_hint(err: Exception) -> None:
    """Convert common "table missing" DB errors into a clearer message.

    This mainly helps local development when the backend code is updated but
    Alembic migrations haven't been applied yet.
    """

    if settings.environment != "development":
        return

    if not isinstance(err, (OperationalError, ProgrammingError)):
        return

    msg = str(getattr(err, "orig", err))
    msg_l = msg.lower()
    if "wallet_accounts" in msg_l or "wallet_transactions" in msg_l or "doesn't exist" in msg_l or "does not exist" in msg_l:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Wallet tables are missing or out of date. Run `alembic upgrade head` (from backend/.venv) and retry.",
        ) from err


def _get_dev_customer_id(db: Session) -> int | None:
    # Keep behavior consistent with cart/profile dev flows.
    u = db.execute(select(User).where(User.email == "customer@example.com")).scalars().first()
    return int(u.id) if u else None


def _require_user_id(db: Session, current_user: User | None) -> int:
    uid = int(current_user.id) if current_user else _get_dev_customer_id(db)
    if uid is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return uid


def _get_or_create_account(db: Session, *, user_id: int) -> WalletAccount:
    acct = db.execute(select(WalletAccount).where(WalletAccount.user_id == user_id)).scalars().first()
    if acct:
        return acct
    acct = WalletAccount(user_id=user_id, balance=0, currency="INR")
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return acct


def _txn_to_response(tx: WalletTransaction) -> WalletTransactionResponse:
    return WalletTransactionResponse(
        id=int(tx.id),
        direction=tx.direction,
        txn_type=tx.txn_type,
        amount=str(Decimal(str(tx.amount or 0)).quantize(Decimal("0.01"))),
        currency=tx.currency,
        reference=tx.reference,
        description=tx.description,
        created_at=tx.created_at,
    )


@router.get("/balance", response_model=WalletBalanceResponse)
def get_balance(db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    try:
        uid = _require_user_id(db, current_user)
        acct = _get_or_create_account(db, user_id=uid)
        bal = Decimal(str(acct.balance or 0)).quantize(Decimal("0.01"))
        return WalletBalanceResponse(balance=str(bal), currency=acct.currency)
    except Exception as e:
        _maybe_raise_migration_hint(e)
        raise


@router.get("/transactions", response_model=WalletTransactionsResponse)
def list_transactions(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    try:
        uid = _require_user_id(db, current_user)
        acct = _get_or_create_account(db, user_id=uid)

        txns = (
            db.execute(
                select(WalletTransaction)
                .where(WalletTransaction.user_id == uid)
                .order_by(WalletTransaction.id.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )

        bal = Decimal(str(acct.balance or 0)).quantize(Decimal("0.01"))
        return WalletTransactionsResponse(
            balance=str(bal),
            currency=acct.currency,
            transactions=[_txn_to_response(t) for t in txns],
        )
    except Exception as e:
        _maybe_raise_migration_hint(e)
        raise


@router.post("/topup", response_model=WalletTopupResponse)
def topup_wallet(
    payload: WalletTopupRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    try:
        uid = _require_user_id(db, current_user)

        # Lock account row for safe increment
        acct = (
            db.execute(select(WalletAccount).where(WalletAccount.user_id == uid).with_for_update())
            .scalars()
            .first()
        )
        if not acct:
            acct = WalletAccount(user_id=uid, balance=0, currency=payload.currency or "INR")
            db.add(acct)
            db.flush()

        if payload.currency != acct.currency:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Wallet currency mismatch. Expected {acct.currency}",
            )

        amt = Decimal(str(payload.amount)).quantize(Decimal("0.01"))
        if amt <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount must be positive")

        acct.balance = float((Decimal(str(acct.balance or 0)) + amt).quantize(Decimal("0.01")))

        tx = WalletTransaction(
            account_id=int(acct.id),
            user_id=uid,
            direction=WalletTxnDirection.IN_.value,
            txn_type=WalletTxnType.TOPUP.value,
            amount=float(amt),
            currency=acct.currency,
            reference=None,
            description=payload.description or "Wallet recharge",
        )
        db.add(tx)
        db.commit()
        db.refresh(acct)
        db.refresh(tx)

        bal = Decimal(str(acct.balance or 0)).quantize(Decimal("0.01"))
        return WalletTopupResponse(transaction=_txn_to_response(tx), balance=str(bal), currency=acct.currency)
    except Exception as e:
        _maybe_raise_migration_hint(e)
        raise
