"""Wallet writes share checkout's customer lock and caller-owned transaction."""
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from app.models.wallet import WalletAccount, WalletTransaction


def account_for_checkout(db, checkout):
    account = db.scalar(select(WalletAccount).where(WalletAccount.user_id == checkout.user_id)
                        .with_for_update().execution_options(populate_existing=True))
    if not account:
        account = WalletAccount(user_id=checkout.user_id, balance=0, currency=checkout.currency, payment_mode=checkout.mode)
        db.add(account); db.flush()
    if account.currency != checkout.currency:
        raise HTTPException(409, 'Wallet currency does not match checkout')
    if account.payment_mode and account.payment_mode != checkout.mode:
        raise HTTPException(409, 'Wallet belongs to a different payment mode. Reconcile it before switching modes.')
    if not account.payment_mode and Decimal(account.balance) != 0 and checkout.mode != 'test':
        raise HTTPException(409, 'Legacy wallet credits must be reconciled before live recharges.')
    account.payment_mode = checkout.mode
    return account


def credit_wallet(db, checkout):
    existing = db.scalar(select(WalletTransaction).where(WalletTransaction.checkout_id == checkout.id))
    if existing:
        return
    account = account_for_checkout(db, checkout)
    account.balance = Decimal(account.balance) + checkout.amount
    db.add(WalletTransaction(account_id=account.id, user_id=checkout.user_id, checkout_id=checkout.id,
        direction='IN', txn_type='TOPUP', amount=checkout.amount, currency=checkout.currency,
        reference=checkout.gateway_payment_id, description=f'{checkout.provider} wallet recharge ({checkout.mode})'))


def refund_wallet(db, checkout, refunded_minor):
    credit = db.scalar(select(WalletTransaction).where(WalletTransaction.checkout_id == checkout.id))
    if not credit:
        return  # Refund before fulfillment: no balance was granted.
    previous = int(checkout.snapshot.get('wallet_refunded_minor', 0))
    if refunded_minor <= previous:
        return
    if refunded_minor > int(checkout.amount * 100):
        raise HTTPException(409, 'Refund exceeds wallet recharge amount')
    account = account_for_checkout(db, checkout)
    delta = Decimal(refunded_minor - previous) / 100
    # A spent top-up can be refunded at the gateway. Preserve the debt, not free
    # credits: existing balance checks prevent spending a negative balance.
    account.balance = Decimal(account.balance) - delta
    db.add(WalletTransaction(account_id=account.id, user_id=checkout.user_id, direction='OUT', txn_type='REFUND_REVERSAL',
        amount=delta, currency=checkout.currency, reference=f'refund:{checkout.id}:{refunded_minor}',
        description='Gateway recharge refund reversal'))
    checkout.snapshot = {**checkout.snapshot, 'wallet_refunded_minor': refunded_minor}