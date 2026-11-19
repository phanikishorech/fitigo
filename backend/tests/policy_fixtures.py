"""Explicit test funding evidence; never used by application code."""
from decimal import Decimal
from sqlalchemy import select
from app.models.booking import Booking, Payment
from app.models.wallet import WalletAccount, WalletTransaction


def fund_wallet_booking(db, booking_id):
    """Represent a verified debit for a confirmed fixture, with balanced ledger."""
    booking = db.get(Booking, booking_id)
    account = db.scalar(select(WalletAccount).where(WalletAccount.user_id == booking.user_id))
    amount = Decimal(str(booking.total_price))
    if account is None:
        account = WalletAccount(user_id=booking.user_id, balance=amount, currency=booking.currency, payment_mode='test')
        db.add(account); db.flush()
        db.add(WalletTransaction(account_id=account.id, user_id=booking.user_id, direction='IN', txn_type='TOPUP',
            amount=amount, currency=booking.currency, reference='test-fixture-funding'))
    assert account.currency == booking.currency and Decimal(str(account.balance)) >= amount
    account.balance = Decimal(str(account.balance)) - amount
    debit = WalletTransaction(account_id=account.id, user_id=booking.user_id, direction='OUT', txn_type='PAYMENT',
        amount=amount, currency=booking.currency, reference=f'test-fixture-booking:{booking_id}')
    db.add(debit); db.flush()
    payment = db.scalar(select(Payment).where(Payment.booking_id == booking_id))
    if payment is None:
        payment = Payment(booking_id=booking_id, amount=amount, currency=booking.currency)
        db.add(payment)
    payment.provider, payment.status, payment.external_ref = 'WALLET', 'PAID', f'WALLET_TXN:{debit.id}'
    booking.status = 'CONFIRMED'
    db.flush()
    return debit