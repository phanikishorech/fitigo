from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.booking import Booking, BookingStatus, Payment, PaymentStatus
from app.models.gym import Gym
from app.repositories.user_repository import UserRepository
from app.core.roles import ROLE_CUSTOMER, ROLE_GYM_OWNER
from app.core.time import ist_day_bounds, ist_today
from app.core.reporting_range import reporting_range
from app.services.admin_revenue import gateway_booking_amount, eligible_admin_payment, admin_revenue_scope


class AdminDashboardService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)

    def summary(self, *, date_from: date | None = None, date_to: date | None = None) -> dict:
        first, last = reporting_range(date_from, date_to) or (ist_today(), ist_today())
        start, end = ist_day_bounds(first)[0], ist_day_bounds(last)[1]
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
        today = ist_today()
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

        # Attended gross service value, not gateway cash or platform net revenue.
        start_day = today - timedelta(days=29)
        from app.core.config import settings
        from app.services.admin_financial_queries import attended_values
        values = attended_values(self.db, settings.gateway_mode)
        revenue_30d = self.db.scalar(select(func.coalesce(func.sum(values.c.total), 0)).where(
            values.c.event_at >= ist_day_bounds(start_day)[0].replace(tzinfo=None),
            values.c.event_at < ist_day_bounds(today)[1].replace(tzinfo=None)))

        users_in_period = self.db.scalar(select(func.count()).select_from(User)
            .where(User.created_at >= start, User.created_at < end))
        gyms_in_period = self.db.scalar(select(func.count()).select_from(Gym)
            .where(Gym.created_at >= start, Gym.created_at < end))
        period_filter = Booking.slot_date.between(first, last)
        bookings_in_period = self.db.scalar(select(func.count()).select_from(Booking).where(period_filter))
        confirmed_in_period = self.db.scalar(select(func.count()).select_from(Booking)
            .where(period_filter, Booking.status == BookingStatus.CONFIRMED.value))
        revenue_in_period = self.db.scalar(select(func.coalesce(func.sum(values.c.total), 0)).where(
            values.c.event_at >= start.replace(tzinfo=None), values.c.event_at < end.replace(tzinfo=None)))
        return {
            "date_from": first.isoformat(),
            "date_to": last.isoformat(),
            "users": {
                "in_period": int(users_in_period or 0),
                "total": int(users_total or 0),
                "customers": int(customers_total or 0),
                "gym_owners": int(owners_total or 0),
            },
            "gyms": {
                "in_period": int(gyms_in_period or 0),
                "total": int(gyms_total or 0),
                "pending_approval": int(gyms_pending or 0),
            },
            "bookings": {
                "in_period": int(bookings_in_period or 0),
                "confirmed_in_period": int(confirmed_in_period or 0),
                "today": int(bookings_today or 0),
                "upcoming": int(upcoming_bookings or 0),
            },
            "revenue": {
                **admin_revenue_scope(),
                'date_basis': 'FIRST_VALID_CHECKIN',
                'basis': 'Verified attended gross booking value once at first valid QR check-in. Confirmed-only, cancelled and no-show bookings excluded. Not FitiGo net recognized revenue.',
                'recognized_total': None,
                "in_period": str(revenue_in_period),
                "last_30d": str(revenue_30d),
                "currency": "INR",
            },
        }
