from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.gym import Gym
from app.models.membership import GymMembershipPlan, MembershipStatus, UserMembership


class MembershipService:
    def __init__(self, db: Session):
        self.db = db

    def create_plan(self, *, owner_user_id: int, gym_id: int, data: dict) -> GymMembershipPlan:
        gym = self.db.execute(select(Gym).where(Gym.id == gym_id, Gym.owner_user_id == owner_user_id)).scalars().first()
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

        plan = GymMembershipPlan(
            pause_allowed=data.get("pause_policy", {}).get("allowed", False),
            max_pause_days=data.get("pause_policy", {}).get("max_pause_days", 0),
            gym_id=gym_id,
            name=data["name"],
            description=data.get("description"),
            duration_days=int(data["duration_days"]),
            price=Decimal(str(data["price"])),
            currency=data.get("currency") or "INR",
            is_active=True,
        )
        self.db.add(plan)
        self.db.commit()
        self.db.refresh(plan)
        return plan

    def list_public_plans(self, *, gym_id: int) -> list[GymMembershipPlan]:
        gym = self.db.execute(select(Gym).where(Gym.id == gym_id, Gym.status == "APPROVED", Gym.is_active.is_(True))).scalars().first()
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")
        return list(
            self.db.execute(
                select(GymMembershipPlan)
                .where(GymMembershipPlan.gym_id == gym_id, GymMembershipPlan.is_active.is_(True))
                .order_by(GymMembershipPlan.id.desc())
            )
            .scalars()
            .all()
        )

    def list_owner_plans(self, *, owner_user_id: int, gym_id: int) -> list[GymMembershipPlan]:
        """Owner listing of membership plans.

        Unlike the public endpoint, this does not require APPROVED status and includes
        both active and inactive plans.
        """

        gym = self.db.execute(select(Gym).where(Gym.id == gym_id, Gym.owner_user_id == owner_user_id)).scalars().first()
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

        return list(
            self.db.execute(select(GymMembershipPlan).where(GymMembershipPlan.gym_id == gym_id).order_by(GymMembershipPlan.id.desc()))
            .scalars()
            .all()
        )

    def update_plan(self, *, owner_user_id: int, plan_id: int, data: dict) -> GymMembershipPlan:
        plan = (
            self.db.execute(
                select(GymMembershipPlan)
                .join(Gym, Gym.id == GymMembershipPlan.gym_id)
                .where(GymMembershipPlan.id == plan_id, Gym.owner_user_id == owner_user_id)
            )
            .scalars()
            .first()
        )
        if not plan:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

        if "name" in data and data["name"] is not None:
            plan.name = data["name"]
        if "description" in data:
            plan.description = data.get("description")
        if "duration_days" in data and data["duration_days"] is not None:
            plan.duration_days = int(data["duration_days"])
        if "price" in data and data["price"] is not None:
            plan.price = Decimal(str(data["price"]))
        if "currency" in data and data["currency"] is not None:
            plan.currency = data["currency"]
        if "is_active" in data and data["is_active"] is not None:
            plan.is_active = bool(data["is_active"])
        if data.get("pause_policy") is not None:
            plan.pause_allowed = data["pause_policy"]["allowed"]
            plan.max_pause_days = data["pause_policy"]["max_pause_days"]

        self.db.commit()
        self.db.refresh(plan)
        return plan

    def set_plan_active(self, *, owner_user_id: int, plan_id: int, active: bool) -> GymMembershipPlan:
        plan = (
            self.db.execute(
                select(GymMembershipPlan)
                .join(Gym, Gym.id == GymMembershipPlan.gym_id)
                .where(GymMembershipPlan.id == plan_id, Gym.owner_user_id == owner_user_id)
            )
            .scalars()
            .first()
        )
        if not plan:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
        plan.is_active = bool(active)
        self.db.commit()
        self.db.refresh(plan)
        return plan

    def purchase_membership(self, *, user_id: int, gym_id: int, plan_id: int) -> UserMembership:
        # Legacy internal callers must not bypass wallet acceptance/debit.
        raise HTTPException(status_code=409, detail={"code": "MEMBERSHIP_PRICE_CHANGED"})

    def list_my_memberships(self, *, user_id: int) -> list[UserMembership]:
        return list(
            self.db.execute(select(UserMembership).where(UserMembership.user_id == user_id).order_by(UserMembership.id.desc()))
            .scalars()
            .all()
        )

    def cancel_membership(self, *, user_id: int, membership_id: int) -> UserMembership:
        from app.models.auth import User
        self.db.scalars(select(User).where(User.id == user_id).with_for_update()).first()
        m = self.db.execute(select(UserMembership).where(UserMembership.id == membership_id, UserMembership.user_id == user_id).with_for_update().execution_options(populate_existing=True)).scalars().first()
        if not m:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
        if m.status != MembershipStatus.ACTIVE.value:
            return m
        m.status = MembershipStatus.CANCELLED.value
        m.cancelled_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(m)
        return m
