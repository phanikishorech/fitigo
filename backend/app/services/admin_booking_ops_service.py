from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus, Payment, PaymentStatus
from app.models.slot import GymSlot, SlotAvailability, SlotAvailabilityStatus


class AdminBookingOpsService:
    def __init__(self, db: Session):
        self.db = db

    def cancel_booking(self, *, booking_id: int, reason: str | None = None) -> Booking:
        booking = self.db.execute(select(Booking).where(Booking.id == booking_id)).scalars().first()
        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

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
            if payment and payment.status == PaymentStatus.PAID.value:
                payment.status = PaymentStatus.REFUNDED.value

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
    ) -> Booking:
        booking = self.db.execute(select(Booking).where(Booking.id == booking_id)).scalars().first()
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

            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        self.db.refresh(booking)
        return booking
