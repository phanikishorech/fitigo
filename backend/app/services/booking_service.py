from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus, Payment, PaymentStatus
from app.models.gym import Gym
from app.models.auth import User
from app.models.slot import GymSlot, SlotAvailability, SlotAvailabilityStatus


class BookingService:
    def __init__(self, db: Session):
        self.db = db

    def _now(self) -> datetime:
        # MySQL DATETIME does not preserve timezone; SQLAlchemy often returns naive datetimes.
        # Use naive UTC consistently to avoid naive/aware comparison errors.
        return datetime.utcnow()

    def _expire_pending_for_slot_date_locked(self, *, gym_slot_id: int, slot_date, av: SlotAvailability, slot: GymSlot) -> None:
        """Expire pending-payment bookings for a slot/date that have passed expires_at.

        Must be called while holding a FOR UPDATE lock on SlotAvailability row.
        """

        now = self._now()
        expired = (
            self.db.execute(
                select(Booking)
                .where(
                    Booking.gym_slot_id == gym_slot_id,
                    Booking.slot_date == slot_date,
                    Booking.status == BookingStatus.PENDING_PAYMENT.value,
                    Booking.expires_at < now,
                )
                .with_for_update()
            )
            .scalars()
            .all()
        )
        if not expired:
            return

        qty_to_release = sum(int(b.quantity) for b in expired)
        for b in expired:
            b.status = BookingStatus.EXPIRED.value
            b.expired_at = now

        av.booked_count = max(0, int(av.booked_count) - qty_to_release)

        cap_total = av.capacity_override if av.capacity_override is not None else slot.capacity
        remaining = cap_total - av.booked_count - av.blocked_count
        if av.status == SlotAvailabilityStatus.FULL.value and remaining > 0:
            av.status = SlotAvailabilityStatus.AVAILABLE.value

    def create_booking(
        self,
        *,
        user_id: int,
        gym_slot_id: int,
        slot_date,
        quantity: int,
        notes: str | None,
        currency: str = "INR",
        idempotency_key: str | None = None,
        unit_price_override: Decimal | None = None,
        auto_confirm_if_free: bool = False,
    ) -> Booking:
        if quantity <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="quantity must be >= 1")

        if idempotency_key:
            existing = (
                self.db.execute(
                    select(Booking).where(Booking.user_id == user_id, Booking.idempotency_key == idempotency_key)
                )
                .scalars()
                .first()
            )
            if existing:
                return existing

        slot = (
            self.db.execute(select(GymSlot).where(GymSlot.id == gym_slot_id, GymSlot.is_active == 1))
            .scalars()
            .first()
        )
        if not slot:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slot not found")

        gym = self.db.execute(select(Gym).where(Gym.id == slot.gym_id)).scalars().first()
        if not gym or gym.status != "APPROVED" or not gym.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

        # Transaction + row lock to avoid overbooking
        try:
            av = (
                self.db.execute(
                    select(SlotAvailability)
                    .where(SlotAvailability.gym_slot_id == gym_slot_id, SlotAvailability.slot_date == slot_date)
                    .with_for_update()
                )
                .scalars()
                .first()
            )

            if not av:
                av = SlotAvailability(
                    gym_slot_id=gym_slot_id,
                    slot_date=slot_date,
                    capacity_override=None,
                    booked_count=0,
                    blocked_count=0,
                    status=SlotAvailabilityStatus.AVAILABLE.value,
                )
                self.db.add(av)
                self.db.flush()
                # Re-lock the row now that it exists
                av = (
                    self.db.execute(
                        select(SlotAvailability)
                        .where(SlotAvailability.id == av.id)
                        .with_for_update()
                    )
                    .scalars()
                    .one()
                )

            if av.status in {SlotAvailabilityStatus.BLOCKED.value, SlotAvailabilityStatus.CLOSED.value}:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Slot is {av.status}")

            # Release expired pending reservations before capacity check
            self._expire_pending_for_slot_date_locked(gym_slot_id=gym_slot_id, slot_date=slot_date, av=av, slot=slot)

            cap_total = av.capacity_override if av.capacity_override is not None else slot.capacity
            remaining = cap_total - av.booked_count - av.blocked_count
            if remaining < quantity:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not enough capacity")

            unit_price = unit_price_override if unit_price_override is not None else Decimal(str(slot.price))
            total_price = unit_price * Decimal(quantity)

            # TODO: make configurable via settings
            expires_at = self._now() + timedelta(minutes=15)

            booking_status = BookingStatus.PENDING_PAYMENT.value
            payment_status = PaymentStatus.INITIATED.value
            if auto_confirm_if_free and total_price <= Decimal("0"):
                booking_status = BookingStatus.CONFIRMED.value
                payment_status = PaymentStatus.PAID.value

            booking = Booking(
                user_id=user_id,
                gym_id=slot.gym_id,
                gym_slot_id=slot.id,
                slot_date=slot_date,
                quantity=quantity,
                unit_price=unit_price,
                total_price=total_price,
                currency=currency,
                status=booking_status,
                notes=notes,
                expires_at=expires_at,
                expired_at=None,
                idempotency_key=idempotency_key,
            )
            self.db.add(booking)
            self.db.flush()

            payment = Payment(
                booking_id=booking.id,
                provider="DUMMY",
                status=payment_status,
                amount=total_price,
                currency=currency,
                external_ref=None,
            )
            self.db.add(payment)

            # Reserve capacity immediately
            av.booked_count += quantity
            if cap_total - av.booked_count - av.blocked_count <= 0 and av.status == SlotAvailabilityStatus.AVAILABLE.value:
                av.status = SlotAvailabilityStatus.FULL.value

            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        self.db.refresh(booking)
        return booking

    def pay_dummy(self, *, user_id: int, booking_id: int, external_ref: str | None = None) -> Booking:
        booking = self.db.execute(select(Booking).where(Booking.id == booking_id, Booking.user_id == user_id)).scalars().first()
        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

        if booking.status != BookingStatus.PENDING_PAYMENT.value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking is not pending payment")

        # Reject paying expired bookings
        if booking.expires_at < self._now():
            # Mark expired and release capacity
            self.cancel_booking(user_id=user_id, booking_id=booking_id, reason="Expired")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking expired")

        try:
            payment = (
                self.db.execute(select(Payment).where(Payment.booking_id == booking.id).with_for_update())
                .scalars()
                .first()
            )
            if not payment:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Payment not found")

            payment.status = PaymentStatus.PAID.value
            payment.external_ref = external_ref or payment.external_ref
            booking.status = BookingStatus.CONFIRMED.value
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        self.db.refresh(booking)
        return booking

    def cancel_booking(self, *, user_id: int, booking_id: int, reason: str | None = None) -> Booking:
        booking = self.db.execute(select(Booking).where(Booking.id == booking_id, Booking.user_id == user_id)).scalars().first()
        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

        if booking.status in {BookingStatus.CANCELLED.value, BookingStatus.EXPIRED.value}:
            return booking

        if booking.status not in {BookingStatus.PENDING_PAYMENT.value, BookingStatus.CONFIRMED.value}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot cancel booking in status {booking.status}")

        try:
            # Release capacity
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
                av.booked_count = max(0, av.booked_count - booking.quantity)
                if av.status == SlotAvailabilityStatus.FULL.value:
                    cap_total = av.capacity_override
                    if cap_total is None:
                        slot = self.db.execute(select(GymSlot).where(GymSlot.id == booking.gym_slot_id)).scalars().first()
                        cap_total = slot.capacity if slot else None
                    if cap_total is not None and (cap_total - av.booked_count - av.blocked_count) > 0:
                        av.status = SlotAvailabilityStatus.AVAILABLE.value

            if reason == "Expired":
                booking.status = BookingStatus.EXPIRED.value
                booking.expired_at = self._now()
            else:
                booking.status = BookingStatus.CANCELLED.value
                booking.cancelled_at = datetime.utcnow()
            if reason:
                booking.notes = (booking.notes + "\n" if booking.notes else "") + f"Cancel reason: {reason}"

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

    def reschedule_booking(
        self,
        *,
        user_id: int,
        booking_id: int,
        new_gym_slot_id: int,
        new_slot_date,
        note: str | None = None,
    ) -> Booking:
        booking = self.db.execute(select(Booking).where(Booking.id == booking_id, Booking.user_id == user_id)).scalars().first()
        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

        if booking.status in {BookingStatus.CANCELLED.value, BookingStatus.EXPIRED.value}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot reschedule booking in status {booking.status}")

        # Only allow reschedule for pending/confirmed
        if booking.status not in {BookingStatus.PENDING_PAYMENT.value, BookingStatus.CONFIRMED.value}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot reschedule booking in status {booking.status}")

        # Fetch new slot and ensure it's active and belongs to same gym
        new_slot = self.db.execute(select(GymSlot).where(GymSlot.id == new_gym_slot_id, GymSlot.is_active == 1)).scalars().first()
        if not new_slot:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="New slot not found")

        if int(new_slot.gym_id) != int(booking.gym_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reschedule across gyms is not supported")

        gym = self.db.execute(select(Gym).where(Gym.id == booking.gym_id)).scalars().first()
        if not gym or gym.status != "APPROVED" or not gym.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

        if int(new_gym_slot_id) == int(booking.gym_slot_id) and new_slot_date == booking.slot_date:
            return booking

        # Keep pricing consistent for CONFIRMED bookings (payment already done)
        if booking.status == BookingStatus.CONFIRMED.value:
            if Decimal(str(new_slot.price)) != Decimal(str(booking.unit_price)):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot reschedule to a slot with different price")

        # Lock order to avoid deadlocks when swapping slots
        old_key = (int(booking.gym_slot_id), booking.slot_date)
        new_key = (int(new_gym_slot_id), new_slot_date)
        first_key, second_key = (old_key, new_key) if old_key <= new_key else (new_key, old_key)

        def _lock_av(key):
            sid, sdate = key
            av = (
                self.db.execute(
                    select(SlotAvailability)
                    .where(SlotAvailability.gym_slot_id == sid, SlotAvailability.slot_date == sdate)
                    .with_for_update()
                )
                .scalars()
                .first()
            )
            if not av:
                av = SlotAvailability(
                    gym_slot_id=sid,
                    slot_date=sdate,
                    capacity_override=None,
                    booked_count=0,
                    blocked_count=0,
                    status=SlotAvailabilityStatus.AVAILABLE.value,
                )
                self.db.add(av)
                self.db.flush()
                av = (
                    self.db.execute(select(SlotAvailability).where(SlotAvailability.id == av.id).with_for_update())
                    .scalars()
                    .one()
                )
            return av

        try:
            # Lock both rows
            av_first = _lock_av(first_key)
            av_second = _lock_av(second_key)

            # Map locked avs
            av_old = av_first if first_key == old_key else av_second
            av_new = av_first if first_key == new_key else av_second

            # Expire pending reservations on new slot/date
            self._expire_pending_for_slot_date_locked(gym_slot_id=int(new_gym_slot_id), slot_date=new_slot_date, av=av_new, slot=new_slot)

            if av_new.status in {SlotAvailabilityStatus.BLOCKED.value, SlotAvailabilityStatus.CLOSED.value}:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"New slot is {av_new.status}")

            cap_total_new = av_new.capacity_override if av_new.capacity_override is not None else new_slot.capacity
            remaining_new = cap_total_new - av_new.booked_count - av_new.blocked_count
            if remaining_new < int(booking.quantity):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not enough capacity in new slot")

            # Reserve new capacity
            av_new.booked_count += int(booking.quantity)
            if cap_total_new - av_new.booked_count - av_new.blocked_count <= 0 and av_new.status == SlotAvailabilityStatus.AVAILABLE.value:
                av_new.status = SlotAvailabilityStatus.FULL.value

            # Release old capacity
            av_old.booked_count = max(0, int(av_old.booked_count) - int(booking.quantity))
            if av_old.status == SlotAvailabilityStatus.FULL.value:
                old_slot = self.db.execute(select(GymSlot).where(GymSlot.id == booking.gym_slot_id)).scalars().first()
                cap_total_old = av_old.capacity_override if av_old.capacity_override is not None else (old_slot.capacity if old_slot else None)
                if cap_total_old is not None and (cap_total_old - av_old.booked_count - av_old.blocked_count) > 0:
                    av_old.status = SlotAvailabilityStatus.AVAILABLE.value

            # Update booking to new slot/date
            booking.gym_slot_id = int(new_gym_slot_id)
            booking.slot_date = new_slot_date

            if booking.status == BookingStatus.PENDING_PAYMENT.value:
                # Update pricing and payment amount based on new slot price
                unit_price = Decimal(str(new_slot.price))
                total_price = unit_price * Decimal(int(booking.quantity))
                booking.unit_price = unit_price
                booking.total_price = total_price
                booking.expires_at = self._now() + timedelta(minutes=15)

                payment = self.db.execute(select(Payment).where(Payment.booking_id == booking.id).with_for_update()).scalars().first()
                if payment:
                    payment.amount = total_price
                    if payment.status != PaymentStatus.PAID.value:
                        payment.status = PaymentStatus.INITIATED.value

            if note:
                booking.notes = (booking.notes + "\n" if booking.notes else "") + f"Reschedule note: {note}"

            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        self.db.refresh(booking)
        return booking

    def list_owner_gym_bookings(
        self,
        *,
        owner_user_id: int,
        gym_id: int,
        slot_date=None,
        status_filter: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[tuple[Booking, User, GymSlot, Payment | None]]:
        gym = self.db.execute(select(Gym).where(Gym.id == gym_id, Gym.owner_user_id == owner_user_id)).scalars().first()
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

        stmt = (
            select(Booking, User, GymSlot, Payment)
            .join(User, User.id == Booking.user_id)
            .join(GymSlot, GymSlot.id == Booking.gym_slot_id)
            .outerjoin(Payment, Payment.booking_id == Booking.id)
            .where(Booking.gym_id == gym_id)
            .order_by(Booking.id.desc())
            .limit(limit)
            .offset(offset)
        )
        if slot_date is not None:
            stmt = stmt.where(Booking.slot_date == slot_date)
        if status_filter is not None:
            stmt = stmt.where(Booking.status == status_filter)

        rows = self.db.execute(stmt).all()
        return [(b, u, s, p) for (b, u, s, p) in rows]

    def get_owner_booking(
        self,
        *,
        owner_user_id: int,
        booking_id: int,
    ) -> tuple[Booking, User, GymSlot, Payment | None]:
        row = (
            self.db.execute(
                select(Booking, User, GymSlot, Payment)
                .join(Gym, Gym.id == Booking.gym_id)
                .join(User, User.id == Booking.user_id)
                .join(GymSlot, GymSlot.id == Booking.gym_slot_id)
                .outerjoin(Payment, Payment.booking_id == Booking.id)
                .where(Booking.id == booking_id, Gym.owner_user_id == owner_user_id)
            )
            .first()
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
        b, u, s, p = row
        return b, u, s, p

    def owner_cancel_booking(self, *, owner_user_id: int, booking_id: int, reason: str | None = None) -> Booking:
        # Resolve booking + verify ownership via join on gyms
        booking = (
            self.db.execute(
                select(Booking)
                .join(Gym, Gym.id == Booking.gym_id)
                .where(Booking.id == booking_id, Gym.owner_user_id == owner_user_id)
            )
            .scalars()
            .first()
        )
        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

        if booking.status in {BookingStatus.CANCELLED.value, BookingStatus.EXPIRED.value}:
            return booking

        if booking.status not in {BookingStatus.PENDING_PAYMENT.value, BookingStatus.CONFIRMED.value}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot cancel booking in status {booking.status}")

        try:
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
                    cap_total = av.capacity_override
                    if cap_total is None:
                        slot = self.db.execute(select(GymSlot).where(GymSlot.id == booking.gym_slot_id)).scalars().first()
                        cap_total = slot.capacity if slot else None
                    if cap_total is not None and (cap_total - av.booked_count - av.blocked_count) > 0:
                        av.status = SlotAvailabilityStatus.AVAILABLE.value

            booking.status = BookingStatus.CANCELLED.value
            booking.cancelled_at = datetime.utcnow()
            if reason:
                booking.notes = (booking.notes + "\n" if booking.notes else "") + f"Owner cancel reason: {reason}"

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

    def owner_mark_attendance(
        self,
        *,
        owner_user_id: int,
        booking_id: int,
        attendance_status: str,
        note: str | None = None,
    ) -> Booking:
        booking = (
            self.db.execute(
                select(Booking)
                .join(Gym, Gym.id == Booking.gym_id)
                .where(Booking.id == booking_id, Gym.owner_user_id == owner_user_id)
            )
            .scalars()
            .first()
        )
        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

        if booking.status != BookingStatus.CONFIRMED.value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only CONFIRMED bookings can be marked")

        if attendance_status not in {"ATTENDED", "NO_SHOW"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid attendance_status")

        booking.attendance_status = attendance_status
        booking.attendance_marked_at = self._now()
        if note is not None:
            booking.attendance_note = note
        self.db.commit()
        self.db.refresh(booking)
        return booking
