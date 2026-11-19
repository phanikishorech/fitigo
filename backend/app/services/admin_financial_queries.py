"""Read-only financial evidence projections. Never reconcile or mutate on a GET."""
from sqlalchemy import and_, case, exists, func, literal, or_, select, union_all
from app.models.access import AccessQrToken, Checkin, CustomerDailyAccess
from app.models.booking import Booking, Payment
from app.models.checkout_funding import BookingFunding, CheckoutFunding
from app.models.membership import UserMembership
from app.models.payment_checkout import PaymentAttempt, PaymentCheckout
from app.models.wallet import WalletTransaction


def paid_checkouts(db, mode):
    """Only fully verified, unrefunded, fulfilled purchase funding. One row/order."""
    from app.services.checkout_funding import available
    success = exists(select(PaymentAttempt.id).where(
        PaymentAttempt.checkout_id == PaymentCheckout.id,
        PaymentAttempt.external_id == PaymentCheckout.gateway_payment_id,
        PaymentAttempt.currency == PaymentCheckout.currency,
        PaymentAttempt.amount == PaymentCheckout.amount, PaymentAttempt.status == 'SUCCESS',
        PaymentAttempt.refunded_amount == 0))
    adverse = exists(select(PaymentAttempt.id).where(PaymentAttempt.checkout_id == PaymentCheckout.id,
        or_(PaymentAttempt.refunded_amount > 0, and_(PaymentAttempt.status == 'SUCCESS',
            or_(PaymentAttempt.external_id != PaymentCheckout.gateway_payment_id,
                PaymentAttempt.amount != PaymentCheckout.amount, PaymentAttempt.currency != 'INR')))))
    base = [PaymentCheckout.mode == mode, PaymentCheckout.currency == 'INR',
        PaymentCheckout.provider.in_(['RAZORPAY', 'CASHFREE']), PaymentCheckout.status == 'PAID', ~adverse]
    if not available(db):
        return select(PaymentCheckout.id.label('checkout_id'), PaymentCheckout.user_id,
            PaymentCheckout.provider, PaymentCheckout.kind, PaymentCheckout.amount.label('total'),
            PaymentCheckout.amount.label('gateway'), literal(0).label('wallet'),
            PaymentCheckout.gateway_payment_id.label('payment_id')).where(*base, success).subquery('verified_funding')
    debit = exists(select(WalletTransaction.id).where(
        WalletTransaction.id == CheckoutFunding.wallet_transaction_id,
        WalletTransaction.checkout_id == PaymentCheckout.id,
        WalletTransaction.user_id == PaymentCheckout.user_id, WalletTransaction.direction == 'OUT',
        WalletTransaction.txn_type == 'PAYMENT', WalletTransaction.currency == 'INR',
        WalletTransaction.amount == CheckoutFunding.wallet_amount))
    valid_funding = or_(CheckoutFunding.checkout_id.is_(None), and_(
        CheckoutFunding.user_id == PaymentCheckout.user_id, CheckoutFunding.mode == mode,
        CheckoutFunding.currency == 'INR', CheckoutFunding.gateway_amount == PaymentCheckout.amount,
        CheckoutFunding.total_amount == CheckoutFunding.wallet_amount + CheckoutFunding.gateway_amount,
        or_(CheckoutFunding.wallet_amount == 0, and_(CheckoutFunding.state == 'DEBITED', debit))))
    return select(PaymentCheckout.id.label('checkout_id'), PaymentCheckout.user_id, PaymentCheckout.provider,
        PaymentCheckout.kind, func.coalesce(CheckoutFunding.total_amount, PaymentCheckout.amount).label('total'),
        PaymentCheckout.amount.label('gateway'), func.coalesce(CheckoutFunding.wallet_amount, 0).label('wallet'),
        PaymentCheckout.gateway_payment_id.label('payment_id')).outerjoin(CheckoutFunding,
            CheckoutFunding.checkout_id == PaymentCheckout.id).where(*base, valid_funding,
                or_(and_(PaymentCheckout.amount > 0, success),
                    and_(PaymentCheckout.amount == 0, CheckoutFunding.wallet_amount > 0, debit))).subquery('verified_funding')


def booking_values(db, mode):
    """Validate cart sums and explicit booking allocations before recognizing value."""
    from app.services.checkout_funding import available
    paid = paid_checkouts(db, mode)
    totals = select(Booking.checkout_id, func.sum(Booking.total_price).label('total'),
        func.min(case((Booking.currency == 'INR', 1), else_=0)).label('inr'),
        func.min(Booking.user_id).label('min_user'), func.max(Booking.user_id).label('max_user'))
    totals = totals.group_by(Booking.checkout_id).subquery('purchase_booking_totals')
    query = select(Booking.id.label('booking_id'), paid.c.provider,
        Booking.total_price.label('total'), paid.c.checkout_id)
    query = query.join(paid, paid.c.checkout_id == Booking.checkout_id).join(totals,
        totals.c.checkout_id == Booking.checkout_id).join(Payment, Payment.booking_id == Booking.id)
    conditions = [paid.c.kind.in_(['BOOKING', 'CART']), paid.c.user_id == Booking.user_id,
        Booking.currency == 'INR', Payment.currency == 'INR', Booking.total_price > 0,
        Booking.total_price == Payment.amount, Payment.status == 'PAID',
        totals.c.total == paid.c.total, totals.c.inr == 1,
        totals.c.min_user == paid.c.user_id, totals.c.max_user == paid.c.user_id,
        Booking.access_source == 'BOOKING_ACCESS',
        or_(and_(paid.c.gateway > 0, Payment.provider == paid.c.provider, Payment.external_ref == paid.c.payment_id),
            and_(paid.c.gateway == 0, Payment.provider == 'WALLET'))]
    if available(db):
        allocated = select(BookingFunding.checkout_id, func.sum(BookingFunding.total_amount).label('total'),
            func.sum(BookingFunding.wallet_amount).label('wallet'), func.sum(BookingFunding.gateway_amount).label('gateway'))
        allocated = allocated.group_by(BookingFunding.checkout_id).subquery('allocated_totals')
        query = query.outerjoin(BookingFunding, BookingFunding.booking_id == Booking.id).outerjoin(allocated,
            allocated.c.checkout_id == paid.c.checkout_id)
        conditions.append(or_(and_(paid.c.wallet == 0, BookingFunding.booking_id.is_(None)), and_(
            BookingFunding.checkout_id == paid.c.checkout_id, BookingFunding.total_amount == Booking.total_price,
            allocated.c.total == paid.c.total, allocated.c.wallet == paid.c.wallet, allocated.c.gateway == paid.c.gateway)))
        query = query.add_columns(func.coalesce(BookingFunding.wallet_amount, 0).label('wallet'),
            func.coalesce(BookingFunding.gateway_amount, Booking.total_price).label('gateway'))
    else:
        query = query.add_columns(literal(0).label('wallet'), Booking.total_price.label('gateway'))
    return query.where(*conditions).subquery('booking_values')


def visits(mode):
    """Deduplicate admissions by purchased visitor or membership daily access.

    Validate durable QR/source links; never use manual attendance as check-in.
    Membership transfer does not rewrite the identity of a historical visitor.
    """
    bookings = select(func.min(Checkin.checkin_time).label('event_at'), Checkin.gym_id,
        Checkin.user_id, Checkin.booking_id, literal('BOOKING').label('category'),
        func.min(Checkin.id).label('visit_id')).join(Booking, Booking.id == Checkin.booking_id)
    bookings = bookings.join(PaymentCheckout, PaymentCheckout.id == Booking.checkout_id).join(
        AccessQrToken, AccessQrToken.id == Checkin.qr_token_id).where(
        Checkin.status == 'SUCCESS', Checkin.access_source == 'BOOKING_ACCESS',
        Booking.status == 'CONFIRMED', or_(Booking.attendance_status.is_(None), Booking.attendance_status != 'NO_SHOW'),
        Checkin.gym_id == Booking.gym_id, Checkin.user_id == Booking.user_id,
        Checkin.visitor_index >= 0, Checkin.visitor_index < Booking.quantity,
        AccessQrToken.booking_id == Booking.id, AccessQrToken.visitor_index == Checkin.visitor_index,
        Checkin.checkin_time >= AccessQrToken.valid_from, Checkin.checkin_time <= AccessQrToken.expires_at,
        PaymentCheckout.mode == mode).group_by(Checkin.gym_id, Checkin.user_id, Checkin.booking_id, Checkin.visitor_index)
    members = select(func.min(Checkin.checkin_time).label('event_at'), Checkin.gym_id,
        Checkin.user_id, literal(None).label('booking_id'), literal('MEMBERSHIP').label('category'),
        func.min(Checkin.id).label('visit_id')).join(CustomerDailyAccess, CustomerDailyAccess.id == Checkin.daily_access_id)
    members = members.join(UserMembership, UserMembership.id == CustomerDailyAccess.membership_id).join(
        PaymentCheckout, PaymentCheckout.id == UserMembership.gateway_checkout_id).join(
        AccessQrToken, AccessQrToken.id == Checkin.qr_token_id).where(
        Checkin.status == 'SUCCESS', Checkin.access_source == 'MEMBERSHIP_ACCESS',
        Checkin.membership_id == CustomerDailyAccess.membership_id,
        Checkin.user_id == CustomerDailyAccess.user_id, CustomerDailyAccess.used_gym_id == Checkin.gym_id,
        AccessQrToken.daily_access_id == CustomerDailyAccess.id,
        Checkin.checkin_time >= AccessQrToken.valid_from, Checkin.checkin_time <= AccessQrToken.expires_at,
        PaymentCheckout.mode == mode).group_by(Checkin.gym_id, Checkin.user_id, Checkin.daily_access_id)
    return union_all(bookings, members).subquery('valid_visits')


def attended_values(db, mode):
    values = booking_values(db, mode)
    admissions = visits(mode)
    first = select(admissions.c.booking_id, func.min(admissions.c.event_at).label('event_at')).where(
        admissions.c.category == 'BOOKING').group_by(admissions.c.booking_id).subquery('first_admission')
    return select(values, Booking.gym_id, Booking.user_id, first.c.event_at).join(
        Booking, Booking.id == values.c.booking_id).join(first, first.c.booking_id == Booking.id).subquery('attended_values')