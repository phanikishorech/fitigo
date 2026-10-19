"""Booking policy for the existing QR/check-in layer. No membership entitlements."""
from datetime import datetime, timedelta, timezone
import secrets

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utcnow, IST, as_ist, stored_instant
from app.models.access import AccessQrToken, AccessSource, Checkin, QrTokenStatus
from app.models.auth import User
from app.models.booking import Booking, BookingStatus, Payment, PaymentStatus
from app.models.slot import GymSlot
from app.models.gym import GymOperatingHours
from app.models.class_booking import GymSpecialHours
from app.services.access_service import _sha256_hex, _token_prefix, _utc


def reject(code: str, message: str, status: int = 400):
    raise HTTPException(status_code=status, detail={"code": code, "message": message})


def validate_visitors(names: list[str] | None, quantity: int):
    if names is not None and (len(names) != quantity or any(not n.strip() or len(n.strip()) > 150 for n in names)):
        reject("INVALID_VISITORS", "Provide one visitor name for each paid place.")
    return [n.strip() for n in names] if names is not None else None


class BookingAccessService:
    def __init__(self, db: Session):
        self.db = db

    def owned(self, booking_id: int, user_id: int) -> Booking:
        booking = self.db.scalar(select(Booking).where(Booking.id == booking_id, Booking.user_id == user_id)
                                 .with_for_update().execution_options(populate_existing=True))
        if not booking:
            reject("BOOKING_NOT_FOUND", "Booking not found.", 404)
        return booking

    def window(self, booking: Booking):
        slot = self.db.get(GymSlot, booking.gym_slot_id)
        if not slot or slot.gym_id != booking.gym_id:
            reject("INVALID_BOOKING", "The booking time is unavailable.")
        start = datetime.combine(booking.slot_date, slot.start_time, tzinfo=IST)
        end = datetime.combine(booking.slot_date, slot.end_time, tzinfo=IST)
        if end <= start:
            end += timedelta(days=1)
        if booking.access_source != AccessSource.BOOKING_ACCESS.value:
            return start, end
        # Scheduled classes retain their session window. Legacy class bookings
        # identify themselves through the existing server-written note metadata.
        metadata = dict(line.split("=", 1) for line in (booking.notes or "").splitlines() if "=" in line)
        if metadata.get("access_type_id") == "GROUP_CLASS" or "class_session_id" in metadata:
            return start, end
        hours = self.db.scalar(select(GymSpecialHours).where(
            GymSpecialHours.gym_id == booking.gym_id, GymSpecialHours.date == booking.slot_date))
        if hours is None:
            hours = self.db.scalar(select(GymOperatingHours).where(
                GymOperatingHours.gym_id == booking.gym_id,
                GymOperatingHours.day_of_week == booking.slot_date.weekday()))
        if hours is not None and hours.is_closed:
            reject("GYM_CLOSED", "The gym is closed on this booking date.")
        if hours is None or not hours.open_time or not hours.close_time:
            reject("GYM_HOURS_UNAVAILABLE", "Gym opening hours are unavailable for this visit.")
        opening = datetime.combine(booking.slot_date, hours.open_time, tzinfo=IST)
        closing = datetime.combine(booking.slot_date, hours.close_time, tzinfo=IST)
        valid_from = max(start - timedelta(hours=1), opening)
        if closing <= opening or valid_from >= closing:
            reject("GYM_HOURS_UNAVAILABLE", "No valid entry window is available for this visit.")
        return valid_from, closing

    def eligibility(self, booking: Booking, *, lock: bool = False) -> tuple[str, str]:
        if booking.access_source != AccessSource.BOOKING_ACCESS.value:
            return "MEMBERSHIP_ACCESS_REQUIRED", "Use My Access for this membership-covered visit."
        if booking.status == BookingStatus.CANCELLED.value:
            return "BOOKING_CANCELLED", "Booking cancelled."
        if booking.status == BookingStatus.EXPIRED.value:
            return "BOOKING_EXPIRED", "This booking has expired."
        if booking.status != BookingStatus.CONFIRMED.value:
            return "BOOKING_NOT_CONFIRMED", "This booking is not confirmed."
        query = select(Payment).where(Payment.booking_id == booking.id)
        payment = self.db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
        if not payment or payment.status != PaymentStatus.PAID.value:
            return "PAYMENT_NOT_COMPLETED", "Payment is not completed or has been refunded."
        if booking.attendance_status == "ATTENDED":
            return "BOOKING_ALREADY_USED", "This booking has already been used."
        try:
            _, expires = self.window(booking)
        except HTTPException as error:
            if isinstance(error.detail, dict):
                return error.detail["code"], error.detail["message"]
            raise
        if utcnow() >= expires:
            return "BOOKING_EXPIRED", "This booking has expired."
        return "READY", "Ready"

    def ensure_records(self, booking: Booking):
        """Called inside confirmation's transaction; never commits the payment early."""
        self.db.flush()
        if booking.access_source != AccessSource.BOOKING_ACCESS.value:
            return
        payment = self.db.scalar(select(Payment).where(Payment.booking_id == booking.id))
        if booking.status != BookingStatus.CONFIRMED.value or not payment or payment.status != PaymentStatus.PAID.value:
            return
        start, end = self.window(booking)
        names = validate_visitors(booking.visitor_names, booking.quantity)
        existing = {row.visitor_index for row in self.db.scalars(select(AccessQrToken).where(AccessQrToken.booking_id == booking.id).with_for_update().execution_options(populate_existing=True))}
        for index in range(booking.quantity):
            if index not in existing:
                self.db.add(AccessQrToken(booking_id=booking.id, visitor_index=index,
                    visitor_name=names[index] if names else None, token_hash=_sha256_hex(secrets.token_urlsafe(32)),
                    valid_from=stored_instant(start), expires_at=stored_instant(end), status=QrTokenStatus.ACTIVE.value))
        self.db.flush()

    def revoke(self, booking: Booking):
        for token in self.db.scalars(select(AccessQrToken).where(AccessQrToken.booking_id == booking.id).with_for_update()):
            if token.status != QrTokenStatus.USED.value:
                token.status = QrTokenStatus.REVOKED.value

    def summary(self, booking: Booking, *, lock: bool = False) -> dict:
        code, message = self.eligibility(booking, lock=lock)
        if code == "READY" and not booking.visitor_names:
            code, message = "VISITOR_DETAILS_REQUIRED", "Add the names of the people using this booking."
        query = select(AccessQrToken).where(AccessQrToken.booking_id == booking.id)
        records = self.db.scalars(query.with_for_update().execution_options(populate_existing=True) if lock else query).all()
        if code == "READY" and records and not any(row.status == QrTokenStatus.ACTIVE.value for row in records):
            code, message = "INVALID_QR", "This booking access is no longer active."
        valid_from, expires_at = (None, None)
        if code in {"READY", "VISITOR_DETAILS_REQUIRED"}:
            valid_from, expires_at = self.window(booking)
        return {"access_type": booking.access_source, "status": code,
                "valid_from": valid_from, "expires_at": expires_at,
                "message": message, "qr_available": code == "READY",
                "passes": [{"qr_id": row.id, "status": row.status, "visitor_name": row.visitor_name,
                            "checked_in_at": as_ist(row.used_at) if row.used_at else None} for row in records],
                "can_set_visitors": code == "VISITOR_DETAILS_REQUIRED"}

    def set_visitors(self, booking_id: int, user_id: int, names: list[str]):
        booking = self.owned(booking_id, user_id)
        code, message = self.eligibility(booking, lock=True)
        if code != "READY":
            reject(code, message)
        if booking.visitor_names:
            reject("VISITORS_ALREADY_SET", "Visitor identities cannot be changed after assignment.")
        booking.visitor_names = validate_visitors(names, booking.quantity)
        self.ensure_records(booking)
        for token in self.db.scalars(select(AccessQrToken).where(AccessQrToken.booking_id == booking.id).with_for_update()):
            token.visitor_name = booking.visitor_names[token.visitor_index]
        self.db.commit()
        return booking

    def issue(self, booking_id: int, user_id: int) -> dict:
        try:
            booking = self.owned(booking_id, user_id)
            summary = self.summary(booking, lock=True)
            if not summary["qr_available"]:
                reject(summary["status"], summary["message"])
            purchaser = self.db.get(User, user_id)
            if not purchaser or purchaser.status != "ACTIVE":
                reject("CUSTOMER_NOT_ELIGIBLE", "Customer is not eligible for entry.")
            self.ensure_records(booking)  # safe backfill for pre-migration confirmed bookings
            start, end = self.window(booking)
            passes = []
            for token in self.db.scalars(select(AccessQrToken).where(AccessQrToken.booking_id == booking.id)
                                         .order_by(AccessQrToken.visitor_index).with_for_update().execution_options(populate_existing=True)):
                raw = None
                if token.status == QrTokenStatus.ACTIVE.value:
                    raw = secrets.token_urlsafe(32)
                    token.token_hash = _sha256_hex(raw)
                    token.valid_from, token.expires_at = stored_instant(start), stored_instant(end)
                    token.generated_at = stored_instant(utcnow())
                passes.append({"qr_id": token.id, "visitor_name": token.visitor_name,
                    "status": token.status, "qr_token": f"{_token_prefix()}{raw}" if raw else None,
                    "valid_from": as_ist(token.valid_from), "expires_at": as_ist(token.expires_at)})
            self.db.commit()
            return {"booking_id": booking.id, "access_type": AccessSource.BOOKING_ACCESS.value, "passes": passes}
        except Exception:
            self.db.rollback()
            raise

    def validate(self, token_hash: str, booking_id: int, gym, scanned_by: int | None) -> dict:
        try:
            # Booking first in ALL write paths; serializes QR issuance, use, refund and cancellation.
            booking = self.db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update()
                                     .execution_options(populate_existing=True))
            if not booking:
                reject("BOOKING_NOT_FOUND", "Booking not found.")
            token = self.db.scalar(select(AccessQrToken).where(AccessQrToken.token_hash == token_hash,
                AccessQrToken.booking_id == booking.id).with_for_update().execution_options(populate_existing=True))
            if not token:
                reject("INVALID_QR", "Invalid QR. Open the current booking QR.")
            code, message = self.eligibility(booking, lock=True)
            if code != "READY":
                reject(code, message)
            if gym.id != booking.gym_id:
                reject("WRONG_GYM", "This booking is not valid at this gym.")
            if token.status == QrTokenStatus.USED.value:
                reject("BOOKING_ALREADY_USED", "This booking access has already been used.", 409)
            if token.status != QrTokenStatus.ACTIVE.value:
                reject("INVALID_QR", "This booking QR is no longer active.")
            if not booking.visitor_names or token.visitor_index is None or token.visitor_index >= len(booking.visitor_names) or token.visitor_name != booking.visitor_names[token.visitor_index]:
                reject("INVALID_VISITOR", "Visitor details do not match this booking.")
            purchaser = self.db.get(User, booking.user_id)
            if not purchaser or purchaser.status != "ACTIVE":
                reject("CUSTOMER_NOT_ELIGIBLE", "Customer is not eligible for entry.")
            now = as_ist(utcnow())
            start, end = self.window(booking)
            if not start.date() <= now.date() <= (end - timedelta(microseconds=1)).date():
                reject("WRONG_DATE", "This booking is not valid on this date.")
            if now < start or now < _utc(token.valid_from):
                reject("OUTSIDE_BOOKING_WINDOW", "The booking entry window has not started.")
            if now >= end or now >= _utc(token.expires_at):
                reject("BOOKING_EXPIRED", "This booking has expired.")
            from app.services.access_service import AccessService
            AccessService(self.db)._validate_checkin_time_window(gym_id=gym.id, at=now)
            checkin = Checkin(user_id=booking.user_id, booking_id=booking.id,
                access_source=AccessSource.BOOKING_ACCESS.value, visitor_index=token.visitor_index,
                visitor_name=token.visitor_name, scanned_by=scanned_by, qr_token_id=token.id,
                gym_id=gym.id, checkin_time=stored_instant(now), status="SUCCESS")
            self.db.add(checkin)
            self.db.flush()
            token.status, token.used_at, token.used_gym_id, token.checkin_id = "USED", stored_instant(now), gym.id, checkin.id
            self.db.flush()
            used = len(self.db.scalars(select(Checkin.id).where(Checkin.booking_id == booking.id).with_for_update()).all())
            if used == booking.quantity:
                booking.attendance_status, booking.attendance_marked_at = "ATTENDED", stored_instant(now)
            self.db.commit()
            return {"success": True, "status": "CHECKED_IN", "customer_name": token.visitor_name,
                    "gym_name": gym.name, "access_type": AccessSource.BOOKING_ACCESS.value,
                    "access_label": "Booking", "access_source": AccessSource.BOOKING_ACCESS.value,
                    "checkin_time": as_ist(checkin.checkin_time)}
        except Exception:
            self.db.rollback()
            raise