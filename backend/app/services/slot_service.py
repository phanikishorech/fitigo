from __future__ import annotations

from datetime import date
from datetime import time as dtime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.gym import Gym
from app.models.slot import GymSlot, SlotAvailability, SlotAvailabilityStatus


class SlotService:
    def __init__(self, db: Session):
        self.db = db

    def create_slot(self, *, owner_user_id: int, gym_id: int, data: dict) -> GymSlot:
        gym = self.db.execute(select(Gym).where(Gym.id == gym_id, Gym.owner_user_id == owner_user_id)).scalars().first()
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

        start_time = data["start_time"]
        end_time = data["end_time"]
        if isinstance(start_time, str):
            start_time = dtime.fromisoformat(start_time)
        if isinstance(end_time, str):
            end_time = dtime.fromisoformat(end_time)
        if end_time <= start_time:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="end_time must be after start_time")

        # Optional scheduling semantics for owner portal (kept backward compatible)
        # - specific_date => create one ClassSession on that date (occasional class)
        # - repeat_days => create ClassSession(s) for the next 30 days matching day(s) (repeating schedule)
        # If neither is provided, we behave like the legacy slot create and only create GymSlot.
        specific_date = data.get("specific_date")
        repeat_days = data.get("repeat_days") or []
        if specific_date is not None and repeat_days:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide either specific_date or repeat_days, not both")

        is_class_schedule = specific_date is not None or bool(repeat_days)

        # Mark gym as class-enabled if scheduling info is provided
        if is_class_schedule and not bool(getattr(gym, "has_classes", False)):
            gym.has_classes = True

        slot = GymSlot(
            gym_id=gym_id,
            name=data["name"],
            start_time=start_time,
            end_time=end_time,
            capacity=int(data["capacity"]),
            price=Decimal(str(data["price"])),
            is_active=1,
        )
        self.db.add(slot)

        # Legacy behaviour: only create GymSlot
        if not is_class_schedule:
            self.db.commit()
            self.db.refresh(slot)
            return slot

        # Create/attach class entities so consumer CLASS booking flow works.
        # We keep using GymSlot as the owner-visible "slot" record for bookings/admin tooling.
        from datetime import timedelta

        from sqlalchemy import func

        from app.models.class_booking import ClassSession, GymClass

        # Find or create class by name for this gym
        gclass = (
            self.db.execute(
                select(GymClass)
                .where(
                    GymClass.gym_id == int(gym.id),
                    func.lower(GymClass.class_name) == str(data["name"]).strip().lower(),
                )
                .limit(1)
            )
            .scalars()
            .first()
        )
        if not gclass:
            gclass = GymClass(gym_id=int(gym.id), class_name=str(data["name"]).strip(), description=None, image_path=None, is_active=True)
            self.db.add(gclass)
            self.db.flush()

        # Create sessions
        price_per_person = Decimal(str(data["price"])).quantize(Decimal("0.01"))
        max_cap = int(data["capacity"])

        to_create: list[date] = []
        if specific_date is not None:
            if isinstance(specific_date, str):
                specific_date = date.fromisoformat(specific_date)
            to_create = [specific_date]
        else:
            # next 30 days for each selected weekday
            d0 = date.today()
            days = {int(d) for d in repeat_days}
            invalid = [d for d in days if d < 0 or d > 6]
            if invalid:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repeat_days must be integers 0..6")
            for i in range(0, 30):
                dt = d0 + timedelta(days=i)
                if dt.weekday() in days:
                    to_create.append(dt)

        for sess_date in to_create:
            # Avoid duplicates (same class/date/time)
            exists = (
                self.db.execute(
                    select(ClassSession.id)
                    .where(
                        ClassSession.gym_class_id == int(gclass.id),
                        ClassSession.session_date == sess_date,
                        ClassSession.start_time == start_time,
                        ClassSession.end_time == end_time,
                        ClassSession.status.notin_(["CANCELLED", "CLOSED"]),
                    )
                    .limit(1)
                )
                .first()
            )
            if exists:
                continue
            self.db.add(
                ClassSession(
                    gym_class_id=int(gclass.id),
                    session_date=sess_date,
                    start_time=start_time,
                    end_time=end_time,
                    maximum_capacity=max_cap,
                    booked_capacity=0,
                    price_per_person=price_per_person,
                    status="AVAILABLE",
                )
            )

        self.db.commit()
        self.db.refresh(slot)
        return slot

    def update_slot(self, *, owner_user_id: int, slot_id: int, data: dict) -> GymSlot:
        slot = self.db.execute(
            select(GymSlot).join(Gym, Gym.id == GymSlot.gym_id).where(GymSlot.id == slot_id, Gym.owner_user_id == owner_user_id)
        ).scalars().first()
        if not slot:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slot not found")

        for k, v in data.items():
            if v is None:
                continue
            if k == "price":
                setattr(slot, k, Decimal(str(v)))
            elif k in {"start_time", "end_time"} and isinstance(v, str):
                setattr(slot, k, dtime.fromisoformat(v))
            elif k == "is_active":
                setattr(slot, k, 1 if v else 0)
            elif k in {"specific_date", "repeat_days"}:
                # Scheduling fields are handled at ClassSession layer; keep ignore here for now.
                # We accept them so the API stays forward compatible with owner UI.
                continue
            else:
                setattr(slot, k, v)

        if slot.end_time <= slot.start_time:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="end_time must be after start_time")

        self.db.commit()
        self.db.refresh(slot)
        return slot

    def deactivate_slot(self, *, owner_user_id: int, slot_id: int) -> None:
        slot = self.db.execute(
            select(GymSlot).join(Gym, Gym.id == GymSlot.gym_id).where(GymSlot.id == slot_id, Gym.owner_user_id == owner_user_id)
        ).scalars().first()
        if not slot:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slot not found")
        slot.is_active = 0
        self.db.commit()

    def list_owner_slots(self, *, owner_user_id: int, gym_id: int) -> list[GymSlot]:
        gym = self.db.execute(select(Gym).where(Gym.id == gym_id, Gym.owner_user_id == owner_user_id)).scalars().first()
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

        return list(
            self.db.execute(select(GymSlot).where(GymSlot.gym_id == gym_id).order_by(GymSlot.start_time.asc(), GymSlot.id.asc()))
            .scalars()
            .all()
        )

    def list_public_slots(self, *, gym_id: int, slot_date: date) -> list[tuple[GymSlot, SlotAvailability]]:
        gym = self.db.execute(select(Gym).where(Gym.id == gym_id, Gym.status == "APPROVED", Gym.is_active.is_(True))).scalars().first()
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

        slots = list(
            self.db.execute(select(GymSlot).where(GymSlot.gym_id == gym_id, GymSlot.is_active == 1).order_by(GymSlot.start_time.asc()))
            .scalars()
            .all()
        )

        result: list[tuple[GymSlot, SlotAvailability]] = []
        for s in slots:
            av = self.db.execute(
                select(SlotAvailability).where(SlotAvailability.gym_slot_id == s.id, SlotAvailability.slot_date == slot_date)
            ).scalars().first()
            if not av:
                av = SlotAvailability(
                    gym_slot_id=s.id,
                    slot_date=slot_date,
                    capacity_override=None,
                    booked_count=0,
                    blocked_count=0,
                    status=SlotAvailabilityStatus.AVAILABLE.value,
                )
                self.db.add(av)
                self.db.flush()
            result.append((s, av))

        self.db.commit()
        return result
