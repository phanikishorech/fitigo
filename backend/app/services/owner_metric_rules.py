"""Shared SQL classification for dashboard totals and paginated booking links."""
from datetime import timedelta
from sqlalchemy import and_, case, exists, or_, select
from app.core.time import ist_now
from app.models.access import Checkin
from app.models.booking import Booking, Payment
from app.models.gym import Gym
from app.models.auth import User
from app.models.slot import GymSlot


def booking_category(now=None):
    now = now or ist_now()
    today, clock = now.date(), now.time().replace(tzinfo=None)
    scanned = exists(select(Checkin.id).where(Checkin.booking_id == Booking.id,
        Checkin.gym_id == Booking.gym_id, Checkin.status == "SUCCESS"))
    # Include visits whose scheduled window is still open (including overnight).
    open_window = or_(Booking.slot_date > today,
        and_(Booking.slot_date == today, or_(GymSlot.end_time > clock, GymSlot.end_time <= GymSlot.start_time)),
        and_(Booking.slot_date == today - timedelta(days=1), GymSlot.end_time <= GymSlot.start_time, GymSlot.end_time > clock))
    return case(
        (Booking.status == "CANCELLED", "cancelled"),
        (and_(Booking.status == "CONFIRMED", Booking.attendance_status == "NO_SHOW"), "no_show"),
        (and_(Booking.status == "CONFIRMED", scanned), "attended"),
        (and_(Booking.status == "CONFIRMED", open_window), "upcoming"),
        (Booking.status == "PENDING_PAYMENT", "pending_payment"),
        (Booking.status == "EXPIRED", "expired"),
        else_="unresolved",
    )


def upcoming_visit_filter(now=None):
    now = now or ist_now()
    future = or_(Booking.slot_date > now.date(), and_(Booking.slot_date == now.date(), GymSlot.start_time > now.time().replace(tzinfo=None)))
    scanned = exists(select(Checkin.id).where(Checkin.booking_id == Booking.id, Checkin.status == 'SUCCESS'))
    paid = exists(select(Payment.id).where(Payment.booking_id == Booking.id, Payment.status == 'PAID'))
    active_customer = exists(select(User.id).where(User.id == Booking.user_id, User.status == 'ACTIVE'))
    return and_(Booking.status == 'CONFIRMED', Booking.access_source == 'BOOKING_ACCESS',
        or_(Booking.attendance_status.is_(None), Booking.attendance_status != 'NO_SHOW'),
        Gym.status == 'APPROVED', Gym.is_active.is_(True), GymSlot.is_active == 1,
        future, ~scanned, paid, active_customer)