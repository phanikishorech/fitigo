from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.booking import Booking, BookingStatus, Payment, PaymentStatus
from app.models.gym import Gym
from app.repositories.user_repository import UserRepository
from app.core.roles import ROLE_CUSTOMER, ROLE_GYM_OWNER


class AdminDashboardService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)

    def summary(self) -> dict:
        # User counts
        users_total = self.db.execute(select(func.count()).select_from(User)).scalar_one()

        # Role counts (simple approach: iterate users by id in DB would be too heavy; do join counts)
        # NOTE: roles are stored in roles/user_roles; easiest is to count distinct mappings.
        from app.models.auth import Role, UserRole

        owners_total = (
            self.db.execute(
                select(func.count(func.distinct(UserRole.user_id)))
                .select_from(UserRole)
                .join(Role, Role.id == UserRole.role_id)
                .where(Role.name == ROLE_GYM_OWNER)
            ).scalar_one()
        )
        customers_total = (
            self.db.execute(
                select(func.count(func.distinct(UserRole.user_id)))
                .select_from(UserRole)
                .join(Role, Role.id == UserRole.role_id)
                .where(Role.name == ROLE_CUSTOMER)
            ).scalar_one()
        )

        # Gym counts
        gyms_total = self.db.execute(select(func.count()).select_from(Gym)).scalar_one()
        gyms_pending = self.db.execute(
            select(func.count()).select_from(Gym).where(Gym.status == "PENDING_APPROVAL")
        ).scalar_one()

        # Booking snapshots
        today = date.today()
        bookings_today = self.db.execute(
            select(func.count()).select_from(Booking).where(Booking.slot_date == today)
        ).scalar_one()
        upcoming_bookings = self.db.execute(
            select(func.count())
            .select_from(Booking)
            .where(
                Booking.slot_date >= today,
                Booking.status.in_([BookingStatus.PENDING_PAYMENT.value, BookingStatus.CONFIRMED.value]),
            )
        ).scalar_one()

        # Revenue last 30 days
        start_day = today - timedelta(days=30)
        revenue_30d = self.db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0))
            .select_from(Payment)
            .join(Booking, Booking.id == Payment.booking_id)
            .where(
                Payment.status == PaymentStatus.PAID.value,
                Booking.slot_date >= start_day,
            )
        ).scalar_one()

        return {
            "users": {
                "total": int(users_total or 0),
                "customers": int(customers_total or 0),
                "gym_owners": int(owners_total or 0),
            },
            "gyms": {
                "total": int(gyms_total or 0),
                "pending_approval": int(gyms_pending or 0),
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
