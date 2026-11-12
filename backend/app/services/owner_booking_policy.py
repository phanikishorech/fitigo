"""One server policy for owner capabilities and mutation revalidation.

Manual attendance is not an admission path. Use the existing scoped QR scanner.
Call under a booking row lock before a mutation; GET capabilities are advisory.
"""
from fastapi import HTTPException
from sqlalchemy import select
from app.core.time import as_ist, utcnow
from app.models.access import Checkin
from app.models.booking import Payment
from app.models.gym import Gym
from app.models.slot import GymSlot
from app.services.booking_access_service import BookingAccessService
from app.schemas.booking import CANCELLATION_MESSAGE


def owner_actions(db, booking, actor_id, *, lock=False):
    reasons = {key: 'You do not own this gym.' for key in ('CANCEL', 'MARK_ATTENDED', 'MARK_NO_SHOW')}
    gym = db.get(Gym, booking.gym_id)
    if not gym or gym.owner_user_id != actor_id:
        return {'allowed_actions': [], 'action_unavailable_reasons': reasons, 'cancellation_policy': CANCELLATION_MESSAGE}
    reasons = {'MARK_ATTENDED': 'Use QR check-in for this gym. Manual attendance does not verify admission or create a completed visit.'}
    query = select(Checkin.id).where(Checkin.booking_id == booking.id, Checkin.status == 'SUCCESS').limit(1)
    used = db.scalar(query.with_for_update() if lock else query)
    slot = db.get(GymSlot, booking.gym_slot_id)
    now = as_ist(utcnow())
    payment_query = select(Payment).where(Payment.booking_id == booking.id)
    payment = db.scalar(payment_query.with_for_update().execution_options(populate_existing=True) if lock else payment_query)
    if booking.status not in {'PENDING_PAYMENT', 'CONFIRMED'}:
        reasons.update(CANCEL='This booking is already closed.', MARK_NO_SHOW='Only a confirmed, paid booking can be marked no-show.')
    elif booking.attendance_status or used:
        reasons.update(CANCEL='Attendance or a successful visit is already recorded; history cannot be overwritten.',
                       MARK_NO_SHOW='Attendance or a successful visit is already recorded; history cannot be overwritten.')
    elif not slot:
        reasons.update(CANCEL='Booking time is unavailable. Contact support.', MARK_NO_SHOW='Booking time is unavailable. Contact support.')
    else:
        # Existing owner cancellation has no time cutoff. Do not invent one;
        # preserve operational cancellation for unused visits, not scanned ones.
        if booking.status != 'CONFIRMED' or not payment or payment.status != 'PAID':
            reasons['MARK_NO_SHOW'] = 'Only a confirmed, paid booking can be marked no-show.'
        else:
            try:
                _, end = BookingAccessService(db).window(booking)
                if now < end:
                    reasons['MARK_NO_SHOW'] = 'The admission window is still open.'
            except HTTPException:
                reasons['MARK_NO_SHOW'] = 'The admission window cannot be verified. Contact support.'
        # Legacy class capacity and gateway-pending settlement need coordinated
        # cancellation; do not expose a partial capacity-release implementation.
        if 'class_session_id=' in (booking.notes or ''):
            reasons['CANCEL'] = 'Class booking cancellation requires coordinated session-capacity review. Contact support.'
        if booking.checkout_id and booking.status == 'PENDING_PAYMENT':
            reasons['CANCEL'] = 'A gateway payment is pending. Resolve checkout before an owner cancellation.'
    return {'allowed_actions': [key for key in ('CANCEL', 'MARK_ATTENDED', 'MARK_NO_SHOW') if key not in reasons],
            'action_unavailable_reasons': reasons, 'cancellation_policy': CANCELLATION_MESSAGE}