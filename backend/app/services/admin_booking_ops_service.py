from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus, Payment, PaymentStatus
from app.models.slot import GymSlot, SlotAvailability, SlotAvailabilityStatus
from app.services.booking_access_service import BookingAccessService
from app.services.booking_time import require_future_start
from app.services.operation_audit import record
from app.services.notification_workflow import publish


class AdminBookingOpsService:
    def __init__(self, db: Session):
        self.db = db

    def cancel_booking(self, *, booking_id: int, reason: str | None = None, actor_id: int | None = None) -> Booking:
        from app.services.booking_cancellation import summary, cancel
        candidate = self.db.get(Booking, booking_id)
        if actor_id is not None and candidate and summary(self.db, candidate)['eligible']:
            # Re-enter the centralized policy before acquiring operational override locks.
            self.db.rollback()
            return cancel(self.db, booking_id=booking_id, actor_id=actor_id, reason=reason)
        # Evidence adds a gym-owner locking read. Preserve the scanner's lock
        # order rather than acquiring gym after booking in the override path.
        from app.services.source_evidence import enabled
        if candidate and enabled(self.db):
            from app.models.auth import User
            from app.models.gym import Gym
            self.db.scalar(select(User).where(User.id == candidate.user_id).with_for_update())
            self.db.scalar(select(Gym).where(Gym.id == candidate.gym_id).with_for_update())
        booking = self.db.execute(select(Booking).where(Booking.id == booking_id).with_for_update().execution_options(populate_existing=True)).scalars().first()
        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

        from app.models.access import Checkin
        if booking.attendance_status or self.db.scalar(select(Checkin.id).where(Checkin.booking_id == booking.id, Checkin.status == 'SUCCESS').limit(1)):
            raise HTTPException(409, 'A used booking cannot be cancelled, including through administrator overrides.')

        if booking.status in {BookingStatus.CANCELLED.value, BookingStatus.EXPIRED.value}:
            return booking

        if booking.status not in {BookingStatus.PENDING_PAYMENT.value, BookingStatus.CONFIRMED.value}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot cancel booking in status {booking.status}")

        try:
            # release capacity
            av = (
                self.db.execute(
                    select(SlotAvailability)
                    .where(SlotAvailability.gym_slot_id == booking.gym_slot_id, SlotAvailability.slot_date == booking.slot_date)
                    .with_for_update()
                )
                .scalars()
                .first()
            )
            if av:
                av.booked_count = max(0, int(av.booked_count) - int(booking.quantity))
                if av.status == SlotAvailabilityStatus.FULL.value:
                    slot = self.db.execute(select(GymSlot).where(GymSlot.id == booking.gym_slot_id)).scalars().first()
                    cap_total = av.capacity_override if av.capacity_override is not None else (slot.capacity if slot else None)
                    if cap_total is not None and (cap_total - av.booked_count - av.blocked_count) > 0:
                        av.status = SlotAvailabilityStatus.AVAILABLE.value

            booking.status = BookingStatus.CANCELLED.value
            booking.cancelled_at = datetime.utcnow()
            if reason:
                booking.notes = (booking.notes + "\n" if booking.notes else "") + f"Admin cancel reason: {reason}"

            payment = (
                self.db.execute(select(Payment).where(Payment.booking_id == booking.id).with_for_update())
                .scalars()
                .first()
            )
            # Preserve payment history: cancellation does not issue a refund.

            BookingAccessService(self.db).revoke(booking)
            record(self.db, 'BOOKING_CANCELLED', booking.id, actor_id, reason_code='ADMIN_REQUEST', gym_id=booking.gym_id)
            publish(self.db, booking.user_id, 'BOOKING_CANCELLED', booking.id)
            from app.services.source_evidence import operational_cancellation
            operational_cancellation(self.db, booking, actor_id)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        self.db.refresh(booking)
        return booking

    def update_payment_status(
        self,
        *,
        booking_id: int,
        new_status: str,
        external_ref: str | None = None,
        note: str | None = None,
        actor_id: int | None = None,
    ) -> Booking:
        booking = self.db.execute(select(Booking).where(Booking.id == booking_id).with_for_update().execution_options(populate_existing=True)).scalars().first()
        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

        try:
            payment = (
                self.db.execute(select(Payment).where(Payment.booking_id == booking.id).with_for_update())
                .scalars()
                .first()
            )
            if not payment:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Payment not found")
            if payment.provider in {"RAZORPAY", "CASHFREE"} or booking.checkout_id:
                raise HTTPException(409, detail="Gateway payment status must be reconciled with the payment provider")
            if payment.provider == 'WALLET' or new_status == PaymentStatus.REFUNDED.value:
                raise HTTPException(409, detail="A status edit cannot perform a wallet transaction or confirm a refund")

            confirming = new_status == PaymentStatus.PAID.value and booking.status == BookingStatus.PENDING_PAYMENT.value
            if confirming:
                slot = self.db.get(GymSlot, booking.gym_slot_id)
                if not slot:
                    raise HTTPException(status_code=404, detail="Slot not found")
                require_future_start(booking.slot_date, slot.start_time)
            payment.status = new_status
            if external_ref is not None:
                payment.external_ref = external_ref

            if note:
                booking.notes = (booking.notes + "\n" if booking.notes else "") + f"Admin payment update: {note}"

            # Keep booking status in sync for common cases
            if new_status == PaymentStatus.PAID.value and booking.status == BookingStatus.PENDING_PAYMENT.value:
                booking.status = BookingStatus.CONFIRMED.value
            if new_status == PaymentStatus.REFUNDED.value and booking.status != BookingStatus.CANCELLED.value:
                booking.status = BookingStatus.CANCELLED.value

            if new_status == PaymentStatus.PAID.value:
                BookingAccessService(self.db).ensure_records(booking)
            else:
                BookingAccessService(self.db).revoke(booking)
            if confirming:
                require_future_start(booking.slot_date, slot.start_time)
            record(self.db, 'PAYMENT_STATUS_CHANGED', booking.id, actor_id, reason_code='ADMIN_REQUEST', to_status=new_status)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        self.db.refresh(booking)
        return booking
