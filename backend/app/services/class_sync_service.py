"""Conservative owner updates: explicit linkage, no customer rescheduling/refunds."""
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.time import IST, ist_now
from app.models.booking import Booking
from app.models.cart import CartItem
from app.models.class_booking import ClassSession, GymClass
from app.models.gym import Gym


def lock_cart_class_gyms(db: Session, user_id):
    """Match owner edits/add-to-cart: gym -> cart -> class session.

    Discovery is read-only; checkout subsequently uses locked current cart reads.
    A concurrently added cart item is revalidated under its session lock.
    """
    gym_ids = list(db.scalars(select(CartItem.gym_id).where(CartItem.user_id == user_id,
        CartItem.booking_type == 'CLASS', CartItem.status == 'ACTIVE').distinct()))
    if gym_ids:
        list(db.scalars(select(Gym).where(Gym.id.in_(gym_ids)).order_by(Gym.id)
            .with_for_update().execution_options(populate_existing=True)))


def conflict(code, message):
    raise HTTPException(409, {'code': code, 'message': message})


def synchronize(db: Session, slot, changes):
    if not changes:
        return
    if slot.sync_kind == 'LEGACY':
        conflict('CLASS_LINK_RECONCILIATION_REQUIRED',
                 'This legacy slot needs an explicitly reviewed session link before editing or deactivation.')
    # Booking display/access uses its slot. Never rewrite old booking times/names.
    if any(key in changes for key in ('name', 'start_time', 'end_time')) and db.scalar(
            select(Booking.id).where(Booking.gym_slot_id == slot.id).limit(1).with_for_update()):
        conflict('SLOT_BOOKING_HISTORY_PROTECTED', 'This slot has booking history. Create a new schedule instead of rewriting its name or time.')
    if slot.sync_kind != 'CLASS':
        return
    now = ist_now()
    for reservation in db.scalars(select(Booking).where(Booking.gym_slot_id == slot.id,
            Booking.status.in_(['PENDING_PAYMENT', 'CONFIRMED'])).with_for_update().execution_options(populate_existing=True)):
        if datetime.combine(reservation.slot_date, slot.start_time, tzinfo=IST) > now:
            conflict('CLASS_HAS_RESERVATIONS', 'No changes saved. Future sessions have bookings or pending payments; resolve them explicitly first.')
    # Discover IDs without locking, then match checkout's cart -> session order.
    session_ids = list(db.scalars(select(ClassSession.id).where(ClassSession.source_slot_id == slot.id)))
    if not session_ids:
        conflict('CLASS_LINK_RECONCILIATION_REQUIRED', 'This class has no linked sessions. Reconcile the schedule before changing it.')
    carts = list(db.scalars(select(CartItem).where(CartItem.class_session_id.in_(session_ids))
        .order_by(CartItem.id).with_for_update().execution_options(populate_existing=True)))
    sessions = list(db.scalars(select(ClassSession).where(ClassSession.source_slot_id == slot.id)
        .order_by(ClassSession.id).with_for_update().execution_options(populate_existing=True)))
    now = ist_now()  # A session may have started while this transaction waited.
    future = [s for s in sessions if datetime.combine(s.session_date, s.start_time, tzinfo=IST) > now
              and s.status not in {'CANCELLED', 'CLOSED'}]
    affected = {s.id for s in future}
    if any(s.booked_capacity > 0 for s in future) or any(c.class_session_id in affected and c.status in {'PAYMENT_PENDING', 'CONFIRMED'} for c in carts):
        conflict('CLASS_HAS_RESERVATIONS', 'No changes saved. Future sessions have bookings or pending payments; resolve them explicitly first.')
    # Some legacy bookings carry the session ID only in server-written metadata.
    for booking in db.scalars(select(Booking).where(Booking.gym_id == slot.gym_id,
            Booking.status.in_(['PENDING_PAYMENT', 'CONFIRMED'])).with_for_update().execution_options(populate_existing=True)):
        metadata = dict(line.split('=', 1) for line in (booking.notes or '').splitlines() if '=' in line)
        if metadata.get('class_session_id') in {str(sid) for sid in affected}:
            conflict('CLASS_HAS_RESERVATIONS', 'No changes saved. Future sessions have bookings or pending payments; resolve them explicitly first.')
    for s in future:
        start, end = changes.get('start_time', s.start_time), changes.get('end_time', s.end_time)
        if datetime.combine(s.session_date, start, tzinfo=IST) <= now or end <= start:
            conflict('CLASS_INVALID_TIME', 'The changed class time must remain in the future and end after its start.')
    # A shared GymClass name is historical data. Clone metadata for future sessions
    # rather than renaming the class referenced by already-started sessions.
    renamed = {}
    for s in future:
        if 'name' in changes:
            if s.gym_class_id not in renamed:
                original = db.get(GymClass, s.gym_class_id)
                clone = GymClass(gym_id=original.gym_id, class_name=changes['name'], description=original.description,
                                 image_path=original.image_path, is_active=original.is_active)
                db.add(clone); db.flush(); renamed[s.gym_class_id] = clone.id
            s.gym_class_id = renamed[s.gym_class_id]
        for source, target in [('start_time', 'start_time'), ('end_time', 'end_time'), ('capacity', 'maximum_capacity'), ('price', 'price_per_person')]:
            if source in changes: setattr(s, target, changes[source])
        if changes.get('is_active') == 0:
            s.status = 'CANCELLED'
    # Active shopping carts are not paid reservations. Invalidate rather than
    # silently moving their selected time/price. Customer must select again.
    for cart in carts:
        if cart.class_session_id in affected and cart.status == 'ACTIVE':
            cart.status = 'REMOVED'
    # Reactivation never resurrects cancelled sessions or historical schedules.