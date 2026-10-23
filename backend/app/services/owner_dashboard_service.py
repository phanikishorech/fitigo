from __future__ import annotations

from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import and_, case, exists, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus, Payment, PaymentStatus
from app.models.gym import Gym
from app.models.access import Checkin, CustomerDailyAccess
from app.models.auth import User
from app.models.membership import UserMembership
from app.core.time import as_ist, ist_day_bounds, ist_today
from app.core.reporting_range import reporting_range


class OwnerDashboardService:
    def __init__(self, db: Session):
        self.db = db

    def _scope(self, owner_user_id: int, gym_id: int | None):
        if gym_id is not None and not self.db.scalar(
            select(Gym.id).where(Gym.id == gym_id, Gym.owner_user_id == owner_user_id)
        ):
            raise HTTPException(status_code=404, detail="Gym not found")
        return and_(Gym.owner_user_id == owner_user_id, Gym.id == gym_id) if gym_id is not None else Gym.owner_user_id == owner_user_id

    def _visits(self, scope, date_from: date, date_to: date):
        start, end = ist_day_bounds(date_from)[0], ist_day_bounds(date_to)[1]
        # Daily access records preserve the access type used at the door, even
        # after the membership expires. Booking scans count each visitor once.
        access_type = func.coalesce(CustomerDailyAccess.access_type, UserMembership.membership_type)
        category = case(
            (Checkin.access_source == "BOOKING_ACCESS", literal("individual_booking")),
            (access_type == "MULTI_GYM", literal("fitigo_member")),
            (access_type == "SINGLE_GYM", literal("single_gym_membership")),
        )
        checkins = (
            select(Checkin.id.label("record_id"), literal("checkin").label("record_type"),
                   Checkin.user_id.label("user_id"), Checkin.gym_id.label("gym_id"),
                   Checkin.booking_id.label("booking_id"), Checkin.visitor_name.label("visitor_name"),
                   Checkin.checkin_time.label("recorded_at"), category.label("category"), literal(1).label("visits"))
            .join(Gym, Gym.id == Checkin.gym_id)
            .outerjoin(CustomerDailyAccess, CustomerDailyAccess.id == Checkin.daily_access_id)
            .outerjoin(UserMembership, UserMembership.id == Checkin.membership_id)
            .where(scope, Checkin.status == "SUCCESS", Checkin.checkin_time >= start,
                   Checkin.checkin_time < end, category.is_not(None))
        )
        # QR validation also marks the booking ATTENDED. Never add the booking's
        # quantity again, including when only some group visitors have checked in.
        scanned = exists(select(Checkin.id).where(Checkin.booking_id == Booking.id, Checkin.status == "SUCCESS"))
        manual = (
            select(Booking.id.label("record_id"), literal("booking").label("record_type"),
                   Booking.user_id.label("user_id"), Booking.gym_id.label("gym_id"),
                   Booking.id.label("booking_id"), literal(None).label("visitor_name"),
                   Booking.attendance_marked_at.label("recorded_at"),
                   literal("individual_booking").label("category"), Booking.quantity.label("visits"))
            .join(Gym, Gym.id == Booking.gym_id)
            .where(scope, Booking.access_source == "BOOKING_ACCESS", Booking.attendance_status == "ATTENDED",
                   Booking.status == BookingStatus.CONFIRMED.value, ~scanned,
                   or_(and_(Booking.attendance_marked_at >= start, Booking.attendance_marked_at < end),
                       and_(Booking.attendance_marked_at.is_(None), Booking.slot_date.between(date_from, date_to))))
        )
        return union_all(checkins, manual).subquery()

    def attendance(self, *, owner_user_id: int, gym_id: int, day: date | None = None, limit: int = 4,
                   date_from: date | None = None, date_to: date | None = None) -> list[dict]:
        first, last = reporting_range(date_from, date_to, day=day) or (ist_today(), ist_today())
        visits = self._visits(self._scope(owner_user_id, gym_id), first, last)
        rows = self.db.execute(
            select(visits, User.first_name, User.last_name)
            .join(User, User.id == visits.c.user_id)
            .order_by(visits.c.recorded_at.desc(), visits.c.record_type, visits.c.record_id.desc())
            .limit(limit)
        ).mappings()
        return [{
            "id": f"{row['record_type']}:{row['record_id']}", "gym_id": row["gym_id"],
            "booking_id": row["booking_id"], "category": row["category"], "visits": row["visits"],
            "customer_name": row["visitor_name"] or " ".join(filter(None, [row["first_name"], row["last_name"]])) or f"Customer #{row['user_id']}",
            "recorded_at": as_ist(row["recorded_at"]).isoformat() if row["recorded_at"] else None,
        } for row in rows]

    def summary(self, *, owner_user_id: int, gym_id: int | None = None, day: date | None = None,
                date_from: date | None = None, date_to: date | None = None) -> dict:
        scope = self._scope(owner_user_id, gym_id)
        first, last = reporting_range(date_from, date_to, day=day) or (ist_today(), ist_today())
        selected_day = first
        # Gym counts
        gym_total = self.db.execute(select(func.count()).select_from(Gym).where(scope)).scalar_one()
        gym_approved = self.db.execute(
            select(func.count()).select_from(Gym).where(scope, Gym.status == "APPROVED")
        ).scalar_one()
        gym_pending = self.db.execute(
            select(func.count()).select_from(Gym).where(scope, Gym.status == "PENDING_APPROVAL")
        ).scalar_one()
        gym_draft = self.db.execute(
            select(func.count()).select_from(Gym).where(scope, Gym.status == "DRAFT")
        ).scalar_one()

        # Booking snapshots
        today = ist_today()
        bookings_today = self.db.execute(
            select(func.count())
            .select_from(Booking)
            .join(Gym, Gym.id == Booking.gym_id)
            .where(scope, Booking.slot_date == today)
        ).scalar_one()

        upcoming_bookings = self.db.execute(
            select(func.count())
            .select_from(Booking)
            .join(Gym, Gym.id == Booking.gym_id)
            .where(
                scope,
                Booking.slot_date >= today,
                Booking.status.in_([BookingStatus.PENDING_PAYMENT.value, BookingStatus.CONFIRMED.value]),
            )
        ).scalar_one()

        # Revenue (dummy payment impl) - count PAID payments in last 30 days
        start_day = today - timedelta(days=30)
        revenue_30d = self.db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0))
            .select_from(Payment)
            .join(Booking, Booking.id == Payment.booking_id)
            .join(Gym, Gym.id == Booking.gym_id)
            .where(
                scope,
                Payment.status == PaymentStatus.PAID.value,
                Booking.slot_date >= start_day,
            )
        ).scalar_one()

        bookings_on_date = self.db.scalar(select(func.count()).select_from(Booking)
            .join(Gym, Gym.id == Booking.gym_id).where(scope, Booking.slot_date == selected_day))
        period_filter = Booking.slot_date.between(first, last)
        bookings_in_period = self.db.scalar(select(func.count()).select_from(Booking)
            .join(Gym, Gym.id == Booking.gym_id).where(scope, period_filter))
        confirmed_in_period = self.db.scalar(select(func.count()).select_from(Booking)
            .join(Gym, Gym.id == Booking.gym_id)
            .where(scope, period_filter, Booking.status == BookingStatus.CONFIRMED.value))
        revenue_in_period = self.db.scalar(select(func.coalesce(func.sum(Payment.amount), 0))
            .select_from(Payment).join(Booking, Booking.id == Payment.booking_id).join(Gym, Gym.id == Booking.gym_id)
            .where(scope, period_filter, Payment.status == PaymentStatus.PAID.value))
        visits = self._visits(scope, first, last)
        counts = {"fitigo_member": 0, "single_gym_membership": 0, "individual_booking": 0}
        counts.update({category: int(count) for category, count in self.db.execute(
            select(visits.c.category, func.sum(visits.c.visits)).group_by(visits.c.category))})
        counts["total"] = sum(counts.values())
        return {
            "gym_id": gym_id,
            "date": selected_day.isoformat(),
            "date_from": first.isoformat(),
            "date_to": last.isoformat(),
            "visits": counts,
            "gyms": {
                "total": int(gym_total or 0),
                "approved": int(gym_approved or 0),
                "pending_approval": int(gym_pending or 0),
                "draft": int(gym_draft or 0),
            },
            "bookings": {
                "in_period": int(bookings_in_period or 0),
                "confirmed_in_period": int(confirmed_in_period or 0),
                "on_date": int(bookings_on_date or 0),
                "today": int(bookings_today or 0),
                "upcoming": int(upcoming_bookings or 0),
            },
            "revenue": {
                "in_period": str(revenue_in_period),
                "last_30d": str(revenue_30d),
                "currency": "INR",
            },
        }
