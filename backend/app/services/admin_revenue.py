"""Admin paid-booking totals, not owner earned revenue or provider settlements."""
from sqlalchemy import and_, exists, select, func
from app.core.config import settings
from app.models.booking import Booking, Payment
from app.models.payment_checkout import PaymentCheckout


def gateway_booking_amount(db):
    from app.services.checkout_funding import available
    from app.models.checkout_funding import BookingFunding
    if not available(db): return Payment.amount
    allocated = select(BookingFunding.gateway_amount).where(BookingFunding.booking_id == Payment.booking_id).correlate(Payment).scalar_subquery()
    return func.coalesce(allocated, Payment.amount)


def eligible_admin_payment():
    # EXISTS preserves one allocation per booking even for a multi-booking cart.
    # Unlinked legacy records have no trustworthy mode and contribute zero.
    return and_(Payment.status == 'PAID', Payment.currency == 'INR', Payment.amount > 0,
        Booking.currency == 'INR', exists(select(PaymentCheckout.id).where(
            PaymentCheckout.id == Booking.checkout_id,
            PaymentCheckout.user_id == Booking.user_id,
            PaymentCheckout.kind.in_(['BOOKING', 'CART']),
            PaymentCheckout.provider.in_(['RAZORPAY', 'CASHFREE']),
            PaymentCheckout.provider == Payment.provider,
            PaymentCheckout.mode == settings.gateway_mode,
            PaymentCheckout.currency == 'INR',
            PaymentCheckout.status == 'PAID',
            PaymentCheckout.gateway_payment_id.is_not(None))))


def admin_revenue_scope():
    return {'mode': settings.gateway_mode, 'currency': 'INR', 'date_basis': 'SCHEDULED_BOOKING_DATE',
        'basis': 'Verified gateway paid-booking allocations by scheduled date. Cancelled/no-show bookings '
                 'remain included while paid; this is not earned revenue. Refunded, partially refunded, '
                 'review-required, wallet and unlinked legacy payments are excluded. Booking counts cover all modes.'}