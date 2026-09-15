from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus, Payment, PaymentStatus
from app.models.gym import Gym


class OwnerDashboardService:
    def __init__(self, db: Session):
        self.db = db

    def summary(self, *, owner_user_id: int) -> dict:
        # Gym counts
        gym_total = self.db.execute(select(func.count()).select_from(Gym).where(Gym.owner_user_id == owner_user_id)).scalar_one()
        gym_approved = self.db.execute(
            select(func.count()).select_from(Gym).where(Gym.owner_user_id == owner_user_id, Gym.status == "APPROVED")
        ).scalar_one()
        gym_pending = self.db.execute(
            select(func.count()).select_from(Gym).where(Gym.owner_user_id == owner_user_id, Gym.status == "PENDING_APPROVAL")
        ).scalar_one()
        gym_draft = self.db.execute(
            select(func.count()).select_from(Gym).where(Gym.owner_user_id == owner_user_id, Gym.status == "DRAFT")
        ).scalar_one()

        # Booking snapshots
        today = date.today()
        bookings_today = self.db.execute(
            select(func.count())
            .select_from(Booking)
            .join(Gym, Gym.id == Booking.gym_id)
            .where(Gym.owner_user_id == owner_user_id, Booking.slot_date == today)
        ).scalar_one()

        upcoming_bookings = self.db.execute(
            select(func.count())
            .select_from(Booking)
            .join(Gym, Gym.id == Booking.gym_id)
            .where(
                Gym.owner_user_id == owner_user_id,
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
                Gym.owner_user_id == owner_user_id,
                Payment.status == PaymentStatus.PAID.value,
                Booking.slot_date >= start_day,
            )
        ).scalar_one()

        return {
            "gyms": {
                "total": int(gym_total or 0),
                "approved": int(gym_approved or 0),
                "pending_approval": int(gym_pending or 0),
                "draft": int(gym_draft or 0),
            },
            "bookings": {
                "today": int(bookings_today or 0),
                "upcoming": int(upcoming_bookings or 0),
            },
            "revenue": {
                "last_30d": str(revenue_30d),
                "currency": "INR",
            },
        }
