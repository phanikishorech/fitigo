"""One cutoff/credit policy; no gateway side effects. Caller identity is authoritative."""
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from app.core.time import IST, utcnow, as_ist, stored_instant
from app.models.auth import User
from app.models.booking import Booking, Payment
from app.models.customer_policy import BookingCancellation
from app.models.access import Checkin
from app.models.slot import GymSlot, SlotAvailability
from app.models.gym import Gym
from app.models.cart import CartItem
from app.models.class_booking import ClassSession
from app.models.payment_checkout import PaymentCheckout, PaymentAttempt
from app.models.wallet import WalletAccount, WalletTransaction
from app.services.policy_schema import available

POLICY = 'Cancel at least 3 hours before the scheduled start. Eligible paid individual bookings are credited to FitiGo Wallet, not the original payment method.'


def funding(db, booking, payment):
    amount = Decimal(str(booking.total_price))
    if amount == 0:
        if payment and (payment.status != 'PAID' or Decimal(str(payment.amount)) != 0):
            raise ValueError('Payment state is not eligible for cancellation.')
        return Decimal('0.00'), None
    if amount < 0 or not payment or payment.status != 'PAID' or payment.currency != booking.currency or Decimal(str(payment.amount)) != amount:
        raise ValueError('A fully paid, matching booking payment is required. Pending, failed or split/ambiguous payments need review.')
    from app.services import checkout_funding as funding_service
    from app.models.checkout_funding import BookingFunding
    checkout = db.get(PaymentCheckout, booking.checkout_id) if booking.checkout_id else None
    funding = funding_service.get(db, checkout) if checkout else None
    if funding:
        allocation = db.get(BookingFunding, booking.id)
        allocations = list(db.scalars(select(BookingFunding).where(BookingFunding.checkout_id == checkout.id)))
        if (checkout.status != 'PAID' or checkout.user_id != booking.user_id or funding.user_id != booking.user_id
                or funding.currency != booking.currency or checkout.currency != booking.currency or checkout.mode != funding.mode
                or checkout.amount != funding.gateway_amount or not allocation or allocation.checkout_id != checkout.id
                or allocation.total_amount != amount or funding.total_amount != funding.wallet_amount + funding.gateway_amount
                or sum((a.total_amount for a in allocations), Decimal(0)) != funding.total_amount
                or sum((a.wallet_amount for a in allocations), Decimal(0)) != funding.wallet_amount
                or sum((a.gateway_amount for a in allocations), Decimal(0)) != funding.gateway_amount):
            raise ValueError('Verified purchase funding is unavailable.')
        if funding.wallet_amount:
            debit = db.get(WalletTransaction, funding.wallet_transaction_id) if funding.wallet_transaction_id else None
            if funding.state != 'DEBITED' or not debit or debit.user_id != booking.user_id or debit.direction != 'OUT' or debit.txn_type != 'PAYMENT' or debit.amount != funding.wallet_amount or debit.checkout_id != checkout.id or debit.currency != booking.currency:
                raise ValueError('Verified wallet debit is unavailable.')
        if funding.gateway_amount:
            attempts = list(db.scalars(select(PaymentAttempt).where(PaymentAttempt.checkout_id == checkout.id)))
            if payment.provider != checkout.provider or payment.external_ref != checkout.gateway_payment_id or any(a.refunded_amount for a in attempts) or not any(a.external_id == checkout.gateway_payment_id and a.status == 'SUCCESS' and a.amount == funding.gateway_amount and a.currency == booking.currency for a in attempts):
                raise ValueError('Verified gateway contribution is unavailable.')
        return amount, funding.mode
    if payment.provider == 'WALLET':
        prefix = 'WALLET_TXN:'
        ref = payment.external_ref or ''
        debit = db.get(WalletTransaction, int(ref[len(prefix):])) if ref.startswith(prefix) and ref[len(prefix):].isdigit() else None
        if not debit or debit.user_id != booking.user_id or debit.direction != 'OUT' or debit.txn_type != 'PAYMENT' or debit.currency != booking.currency or Decimal(str(debit.amount)) < amount:
            raise ValueError('The original wallet debit could not be verified. Contact support.')
        allocations = list(db.execute(select(Payment.amount, Payment.currency).join(Booking, Booking.id == Payment.booking_id)
            .where(Booking.user_id == booking.user_id, Payment.provider == 'WALLET', Payment.external_ref == ref)))
        if any(currency != debit.currency for _, currency in allocations) or sum((Decimal(str(value)) for value, _ in allocations), Decimal(0)) != Decimal(str(debit.amount)):
            raise ValueError('Wallet payment allocations require review before a credit can be issued.')
        account = db.get(WalletAccount, debit.account_id)
        return amount, account.payment_mode if account else None
    if payment.provider in {'RAZORPAY', 'CASHFREE'}:
        checkout = db.get(PaymentCheckout, booking.checkout_id) if booking.checkout_id else None
        if not checkout or checkout.user_id != booking.user_id or checkout.status != 'PAID' or checkout.mode not in {'test', 'live'} or checkout.provider != payment.provider or checkout.currency != booking.currency or not checkout.gateway_payment_id or payment.external_ref != checkout.gateway_payment_id:
            raise ValueError('The gateway payment allocation is not verified. Contact support.')
        allocations = list(db.execute(select(Booking.total_price, Payment.amount, Payment.currency)
            .join(Payment, Payment.booking_id == Booking.id).where(Booking.checkout_id == checkout.id)))
        if any(Decimal(str(total)) != Decimal(str(paid)) or currency != checkout.currency for total, paid, currency in allocations) or sum((Decimal(str(paid)) for _, paid, _ in allocations), Decimal(0)) != checkout.amount:
            raise ValueError('The booking allocations do not match the paid checkout. Contact support.')
        attempts = list(db.scalars(select(PaymentAttempt).where(PaymentAttempt.checkout_id == checkout.id)))
        if any(a.refunded_amount or a.status in {'REFUNDED', 'PARTIALLY_REFUNDED'} for a in attempts):
            raise ValueError('A provider refund is already recorded. Contact support for reconciliation.')
        if not any(a.external_id == checkout.gateway_payment_id and a.status == 'SUCCESS' and a.amount == checkout.amount and a.currency == checkout.currency for a in attempts):
            raise ValueError('Verified payment evidence is unavailable. Contact support.')
        return amount, checkout.mode
    raise ValueError('This payment source is not eligible for an automatic wallet credit.')


def summary(db, booking, *, now=None, lock=False):
    at = as_ist(now or utcnow())
    slot = db.get(GymSlot, booking.gym_slot_id)
    start = datetime.combine(booking.slot_date, slot.start_time, tzinfo=IST) if slot else None
    deadline = start - timedelta(hours=3) if start else None
    deployed = available(db)
    evidence = db.scalar(select(BookingCancellation).where(BookingCancellation.booking_id == booking.id)) if deployed else None
    result = dict(eligible=False, reason='', deadline=deadline, scheduled_start=start, policy=POLICY,
        refundable_amount='0.00', currency=booking.currency, wallet_credit_amount=str(evidence.amount) if evidence else '0.00',
        wallet_transaction_id=evidence.wallet_transaction_id if evidence else None,
        cancelled_at=as_ist(evidence.created_at) if evidence else as_ist(booking.cancelled_at) if booking.cancelled_at else None,
        cancellation_reason=evidence.reason if evidence else None)
    if not deployed: result['reason'] = 'Cancellation is unavailable until the cancellation policy migration is deployed.'
    elif booking.status != 'CONFIRMED': result['reason'] = 'Only a confirmed booking can be cancelled.'
    elif booking.access_source != 'BOOKING_ACCESS': result['reason'] = 'Membership access cannot be cancelled or refunded.'
    elif booking.attendance_status or db.scalar((select(Checkin.id).where(Checkin.booking_id == booking.id, Checkin.status == 'SUCCESS').limit(1).with_for_update()) if lock else select(Checkin.id).where(Checkin.booking_id == booking.id, Checkin.status == 'SUCCESS').limit(1)):
        result['reason'] = 'Attendance or check-in has already been recorded.'
    elif not deadline: result['reason'] = 'The scheduled start time is unavailable.'
    elif at > deadline: result['reason'] = 'Cancellation is unavailable within 3 hours of the scheduled booking.'
    else:
        try:
            amount, _ = funding(db, booking, db.scalar(select(Payment).where(Payment.booking_id == booking.id)))
            result.update(eligible=True, refundable_amount=str(amount), reason='Cancellation is available until the displayed deadline.')
        except ValueError as error: result['reason'] = str(error)
    return result


def cancel(db, *, booking_id, actor_id, customer_id=None, owner_id=None, reason=None):
    try:
        identity = db.execute(select(Booking.user_id, Booking.gym_id, Booking.checkout_id).where(Booking.id == booking_id)).first()
        if not identity or (customer_id is not None and identity.user_id != customer_id):
            raise HTTPException(404, 'Booking not found')
        # Match payment reconciliation: customer -> checkout -> gym -> booking.
        db.scalar(select(User).where(User.id == identity.user_id).with_for_update().execution_options(populate_existing=True))
        checkout = None
        if identity.checkout_id:
            checkout = db.scalar(select(PaymentCheckout).where(PaymentCheckout.id == identity.checkout_id).with_for_update().execution_options(populate_existing=True))
        gym = db.scalar(select(Gym).where(Gym.id == identity.gym_id).with_for_update().execution_options(populate_existing=True))
        if owner_id is not None and (not gym or gym.owner_user_id != owner_id):
            raise HTTPException(404, 'Booking not found')
        booking = db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update().execution_options(populate_existing=True))
        payment = db.scalar(select(Payment).where(Payment.booking_id == booking_id).with_for_update().execution_options(populate_existing=True))
        policy = summary(db, booking, lock=True)
        if not policy['eligible']: raise HTTPException(409, policy['reason'])
        amount, mode = funding(db, booking, payment)
        transaction = None
        if amount > 0:
            account = db.scalar(select(WalletAccount).where(WalletAccount.user_id == booking.user_id).with_for_update().execution_options(populate_existing=True))
            if not account:
                account = WalletAccount(user_id=booking.user_id, balance=0, currency=booking.currency, payment_mode=mode)
                db.add(account); db.flush()
            if account.currency != booking.currency or (account.payment_mode and mode and account.payment_mode != mode):
                raise HTTPException(409, 'Wallet currency or payment mode differs; cancellation was not applied. Contact support.')
            if not account.payment_mode and mode == 'live' and Decimal(str(account.balance)) != 0:
                raise HTTPException(409, 'Legacy wallet balance requires reconciliation before a live credit.')
            if mode: account.payment_mode = mode
            account.balance = Decimal(str(account.balance)) + amount
            transaction = WalletTransaction(account_id=account.id, user_id=booking.user_id, direction='IN',
                txn_type='CANCELLATION_CREDIT', amount=amount, currency=booking.currency,
                reference=f'booking-cancel:{booking.id}:payment:{payment.id}', description=f'Booking #{booking.id} cancellation credit')
            db.add(transaction); db.flush()
        # Cart class capacity is linked through a server-owned source, never arbitrary request notes.
        source = None
        if booking.idempotency_key and booking.idempotency_key.startswith('cart:'):
            suffix = booking.idempotency_key[5:]
            if suffix.isdigit():
                source = db.scalar(select(CartItem).where(CartItem.id == int(suffix), CartItem.user_id == booking.user_id,
                    CartItem.checkout_id == booking.checkout_id).with_for_update())
        if not source and payment and payment.provider == 'WALLET' and 'class_session_id=' in (booking.notes or ''):
            metadata = dict(line.split('=', 1) for line in (booking.notes or '').splitlines() if '=' in line)
            source_id = metadata.get('cart_item_id', '')
            if source_id.isdigit():
                source = db.scalar(select(CartItem).where(CartItem.id == int(source_id), CartItem.user_id == booking.user_id,
                    CartItem.gym_id == booking.gym_id, CartItem.status == 'CONFIRMED', CartItem.booking_date == booking.slot_date,
                    CartItem.member_count == booking.quantity, CartItem.total_price == booking.total_price).with_for_update())
        if source and source.class_session_id:
            session = db.scalar(select(ClassSession).where(ClassSession.id == source.class_session_id).with_for_update())
            if not session or session.booked_capacity < booking.quantity:
                raise HTTPException(409, 'Class capacity requires review. No cancellation or credit was applied.')
            session.booked_capacity -= booking.quantity
            if session.status == 'FULL': session.status = 'AVAILABLE'
        elif 'class_session_id=' in (booking.notes or ''):
            # Legacy wallet-cart classes lack an immutable FK. Fail without credit rather than release guessed capacity.
            raise HTTPException(409, 'Legacy class capacity needs support review. No cancellation or credit was applied.')
        elif not checkout or checkout.kind != 'CART':
            availability = db.scalar(select(SlotAvailability).where(SlotAvailability.gym_slot_id == booking.gym_slot_id,
                SlotAvailability.slot_date == booking.slot_date).with_for_update())
            if availability:
                availability.booked_count = max(0, availability.booked_count - booking.quantity)
                if availability.status == 'FULL': availability.status = 'AVAILABLE'
        # Recheck the cutoff after all lock waits, before finalizing any change.
        if as_ist(utcnow()) > policy['deadline']: raise HTTPException(409, 'The cancellation deadline has passed. No credit was applied.')
        booking.status, booking.cancelled_at = 'CANCELLED', stored_instant(utcnow())
        db.add(BookingCancellation(booking_id=booking.id, payment_id=payment.id if payment else None,
            wallet_transaction_id=transaction.id if transaction else None, actor_id=actor_id, reason=reason,
            amount=amount, currency=booking.currency, scheduled_start=stored_instant(policy['scheduled_start']),
            deadline=stored_instant(policy['deadline']), created_at=booking.cancelled_at))
        from app.services.booking_access_service import BookingAccessService
        from app.services.notification_workflow import publish
        from app.services.operation_audit import record
        BookingAccessService(db).revoke(booking)
        record(db, 'BOOKING_CANCELLED', booking.id, actor_id, gym_id=booking.gym_id)
        publish(db, booking.user_id, 'BOOKING_CANCELLED', booking.id)
        db.flush()
        from app.services.source_evidence import cancellation
        cancellation(db, booking, db.scalar(select(BookingCancellation).where(BookingCancellation.booking_id == booking.id)))
        db.commit(); db.refresh(booking)
        return booking
    except Exception:
        db.rollback(); raise