from __future__ import annotations

from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.booking import Booking, Payment
from app.models.gym import Gym
from app.models.slot import GymSlot


class AdminBookingService:
    def __init__(self, db: Session):
        self.db = db

    def search(
        self,
        *,
        q: str | None = None,
        gym_id: int | None = None,
        owner_user_id: int | None = None,
        slot_date: date | None = None,
        booking_status: str | None = None,
        payment_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[tuple[Booking, User, Gym, GymSlot, Payment | None]]:
        stmt = (
            select(Booking, User, Gym, GymSlot, Payment)
            .join(User, User.id == Booking.user_id)
            .join(Gym, Gym.id == Booking.gym_id)
            .join(GymSlot, GymSlot.id == Booking.gym_slot_id)
            .outerjoin(Payment, Payment.booking_id == Booking.id)
            .order_by(Booking.id.desc())
            .limit(limit)
            .offset(offset)
        )

        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    User.email.like(like),
                    User.first_name.like(like),
                    User.last_name.like(like),
                    Gym.name.like(like),
                    Gym.city.like(like),
                )
            )
        if gym_id is not None:
            stmt = stmt.where(Booking.gym_id == gym_id)
        if owner_user_id is not None:
            stmt = stmt.where(Gym.owner_user_id == owner_user_id)
        if slot_date is not None:
            stmt = stmt.where(Booking.slot_date == slot_date)
        if booking_status is not None:
            stmt = stmt.where(Booking.status == booking_status)
        if payment_status is not None:
            stmt = stmt.where(Payment.status == payment_status)

        rows = self.db.execute(stmt).all()
        return [(b, u, g, s, p) for (b, u, g, s, p) in rows]

    def get(self, *, booking_id: int) -> tuple[Booking, User, Gym, GymSlot, Payment | None]:
        row = (
            self.db.execute(
                select(Booking, User, Gym, GymSlot, Payment)
                .join(User, User.id == Booking.user_id)
                .join(Gym, Gym.id == Booking.gym_id)
                .join(GymSlot, GymSlot.id == Booking.gym_slot_id)
                .outerjoin(Payment, Payment.booking_id == Booking.id)
                .where(Booking.id == booking_id)
            )
            .first()
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
        b, u, g, s, p = row
        return b, u, g, s, p
