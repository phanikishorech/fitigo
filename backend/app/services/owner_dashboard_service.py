from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import and_, case, func, literal, or_, select
from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus, Payment
from app.models.gym import Gym
from app.models.access import Checkin, CustomerDailyAccess
from app.models.auth import User
from app.models.membership import UserMembership
from app.models.slot import GymSlot
from app.core.time import as_ist, ist_day_bounds, ist_today, ist_now
from app.core.reporting_range import reporting_range
from app.core.config import settings
from app.services.owner_metric_rules import booking_category, upcoming_visit_filter
from app.services.owner_revenue import sales_query


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
            .outerjoin(Booking, Booking.id == Checkin.booking_id)
            .where(scope, Checkin.status == "SUCCESS", Checkin.checkin_time >= start,
                   Checkin.checkin_time < end, category.is_not(None),
                   or_(Checkin.access_source != "BOOKING_ACCESS",
                       and_(Booking.status == "CONFIRMED", Booking.gym_id == Checkin.gym_id,
                            or_(Booking.attendance_status.is_(None), Booking.attendance_status != "NO_SHOW"))))
        )
        # Scanner transactions and unique token/visitor constraints enforce one
        # successful check-in per access. Manual flags/booking quantity are not visits.
        return checkins.subquery()

    def _revenue(self, scope, first, last):
        """Purchase-date cohort, NOT cash settlement or earned-per-visit revenue.

        Both categories use the immutable checkout.created_at. No updated_at
        fallback: reconciliation can update it repeatedly. No refund amount is
        stored, so partially refunded purchases are excluded and disclosed.
        """
        sales = sales_query(scope, first, last).c
        row = self.db.execute(select(
            func.coalesce(func.sum(case((sales.category == 'single_gym_membership', sales.recognized_amount), else_=0)), 0).label('single'),
            func.coalesce(func.sum(case((sales.category == 'individual_booking', sales.recognized_amount), else_=0)), 0).label('individual'),
            func.count(case((sales.payment_status == 'PARTIALLY_REFUNDED', 1))).label('partial'),
            func.coalesce(func.sum(case((and_(sales.payment_status == 'REFUNDED', sales.mode == settings.gateway_mode), sales.amount), else_=0)), 0).label('refunded'),
            func.count(case((and_(sales.payment_status == 'PAID', sales.included == False), 1))).label('excluded'),
        )).one()
        single, individual = Decimal(row.single), Decimal(row.individual)
        return {'single_gym_membership': str(single), 'individual_booking': str(individual),
            'total': str(single + individual), 'currency': 'INR', 'basis': 'PURCHASE_DATE_CURRENT_PAID',
            'mode': settings.gateway_mode,
            'fully_refunded_sales': str(row.refunded), 'partial_refund_count': int(row.partial),
            'excluded_paid_records': int(row.excluded), 'multi_gym_allocation': 'NOT_AVAILABLE'}

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

        bookings_on_date = self.db.scalar(select(func.count()).select_from(Booking)
            .join(Gym, Gym.id == Booking.gym_id).where(scope, Booking.slot_date == selected_day))
        period_filter = Booking.slot_date.between(first, last)
        bookings_in_period = self.db.scalar(select(func.count()).select_from(Booking)
            .join(Gym, Gym.id == Booking.gym_id).where(scope, period_filter))
        confirmed_in_period = self.db.scalar(select(func.count()).select_from(Booking)
            .join(Gym, Gym.id == Booking.gym_id)
            .where(scope, period_filter, Booking.status == BookingStatus.CONFIRMED.value))
        revenue = self._revenue(scope, first, last)
        revenue_30d = self._revenue(scope, today - timedelta(days=29), today)
        category = booking_category(ist_now())
        attendance = {key: 0 for key in ["upcoming", "attended", "cancelled", "no_show", "pending_payment", "expired", "unresolved"]}
        # MySQL ONLY_FULL_GROUP_BY cannot match the repeated CASE containing a
        # correlated EXISTS between SELECT and GROUP BY. Aggregate every selected
        # expression instead; preserve the shared, mutually exclusive classifier.
        attendance = dict(self.db.execute(
            select(*(func.count(case((category == key, 1))).label(key) for key in attendance))
            .select_from(Booking).join(Gym, Gym.id == Booking.gym_id)
            .join(GymSlot, GymSlot.id == Booking.gym_slot_id).where(scope, period_filter)
        ).mappings().one())
        upcoming_visits = self.db.scalar(select(func.coalesce(func.sum(Booking.quantity), 0))
            .select_from(Booking).join(Gym, Gym.id == Booking.gym_id).join(GymSlot, GymSlot.id == Booking.gym_slot_id)
            .where(scope, period_filter, upcoming_visit_filter(ist_now())))
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
            "attendance": attendance,
            "upcoming_visits": int(upcoming_visits),
            "generated_at": ist_now().isoformat(),
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
                "upcoming": attendance["upcoming"],
            },
            "revenue": {**revenue, "in_period": revenue["total"], "last_30d": revenue_30d["total"]},
        }
