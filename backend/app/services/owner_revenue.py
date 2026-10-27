"""One owner-scoped sales projection for summaries, charts and transaction pages."""
from sqlalchemy import and_, case, exists, func, literal, or_, select, union_all
from app.core.config import settings
from app.models.booking import Booking, Payment
from app.models.access import Checkin
from app.models.gym import Gym
from app.models.membership import UserMembership
from app.models.payment_checkout import PaymentCheckout
from app.core.time import ist_day_bounds


def sales_query(scope, first, last):
    start, end = ist_day_bounds(first)[0], ist_day_bounds(last)[1]
    queries = []
    for model, amount, state, link, kind in [
        (Payment, Payment.amount, Payment.status, Booking.checkout_id, 'individual_booking'),
        (UserMembership, UserMembership.paid_amount, UserMembership.payment_status, UserMembership.gateway_checkout_id, 'single_gym_membership'),
    ]:
        paid = and_(state == 'PAID', PaymentCheckout.status == 'PAID', PaymentCheckout.mode == settings.gateway_mode,
            PaymentCheckout.gateway_payment_id.is_not(None), PaymentCheckout.provider.in_(['RAZORPAY', 'CASHFREE']))
        eligible = literal(True)
        if model is Payment:
            # EXISTS avoids multiplying a booking payment by group visitor scans.
            checked_in = exists(select(Checkin.id).where(Checkin.booking_id == Booking.id,
                Checkin.gym_id == Booking.gym_id, Checkin.access_source == 'BOOKING_ACCESS', Checkin.status == 'SUCCESS'))
            eligible = and_(Booking.status == 'CONFIRMED',
                or_(Booking.attendance_status.is_(None), Booking.attendance_status != 'NO_SHOW'), checked_in)
        included = and_(paid, eligible)
        recorded = func.coalesce(PaymentCheckout.created_at, model.created_at)
        query = select(model.id.label('record_id'), literal(kind).label('category'), Gym.id.label('gym_id'),
            Gym.name.label('gym_name'), recorded.label('recorded_at'), amount.label('amount'), state.label('payment_status'),
            model.currency.label('currency'), PaymentCheckout.mode.label('mode'), PaymentCheckout.status.label('checkout_status'),
            case((included, amount), else_=0).label('recognized_amount'), case((included, True), else_=False).label('included'),
            case((~paid, 'PAYMENT_NOT_ELIGIBLE'), (~eligible, 'NO_ELIGIBLE_CHECKIN'), else_=literal(None)).label('exclusion_reason'),
            (Booking.id if model is Payment else literal(None)).label('booking_id'),
            (Booking.user_id if model is Payment else UserMembership.user_id).label('user_id'),
            (Payment.provider if model is Payment else UserMembership.payment_provider).label('provider'),
            PaymentCheckout.gateway_payment_id.label('transaction_id')).select_from(model)
        if model is Payment:
            query = query.join(Booking, Booking.id == Payment.booking_id).join(Gym, Gym.id == Booking.gym_id).where(Booking.access_source == 'BOOKING_ACCESS')
        else:
            query = query.join(Gym, Gym.id == UserMembership.gym_id).where(UserMembership.membership_type == 'SINGLE_GYM')
        queries.append(query.outerjoin(PaymentCheckout, PaymentCheckout.id == link)
            .where(scope, model.currency == 'INR', recorded >= start, recorded < end,
                   # Retain unlinked legacy records for audit, never as revenue.
                   or_(PaymentCheckout.id.is_(None), PaymentCheckout.mode == settings.gateway_mode)))
    return union_all(*queries).subquery('owner_sales')