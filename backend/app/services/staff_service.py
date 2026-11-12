from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.gym import Gym
from app.models.staff import GymStaffAssignment
from app.services.operation_audit import record
from app.services.notification_workflow import publish


class StaffService:
    def __init__(self, db: Session):
        self.db = db

    def invite_staff(self, *, owner_user_id: int, gym_id: int, email: str, first_name: str | None, last_name: str | None) -> dict:
        from app.services.staff_invitation_service import StaffInvitationService
        return StaffInvitationService(self.db).invite(owner_user_id=owner_user_id, gym_id=gym_id,
            email=email, first_name=first_name, last_name=last_name)

    def list_gym_staff(self, *, owner_user_id: int, gym_id: int) -> list[dict]:
        gym = self.db.execute(select(Gym).where(Gym.id == gym_id, Gym.owner_user_id == owner_user_id)).scalars().first()
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")
        # Explicit public fields only. Keep orphaned legacy assignments visible
        # so an owner can revoke them without exposing unrelated user accounts.
        rows = self.db.execute(select(
            GymStaffAssignment.id, GymStaffAssignment.gym_id, GymStaffAssignment.user_id,
            GymStaffAssignment.role, GymStaffAssignment.created_at.label('assigned_at'),
            User.first_name, User.last_name, User.email, User.phone, User.status.label('account_status'),
        ).outerjoin(User, User.id == GymStaffAssignment.user_id)
            .where(GymStaffAssignment.gym_id == gym_id)
            .order_by(GymStaffAssignment.created_at.desc(), GymStaffAssignment.id.desc())).mappings()
        return [dict(row) for row in rows]

    def remove_staff(self, *, owner_user_id: int, gym_id: int, user_id: int) -> None:
        gym = self.db.execute(select(Gym).where(Gym.id == gym_id, Gym.owner_user_id == owner_user_id).with_for_update()).scalars().first()
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")
        assn = (
            self.db.execute(
                select(GymStaffAssignment).where(GymStaffAssignment.gym_id == gym_id, GymStaffAssignment.user_id == user_id).with_for_update()
            )
            .scalars()
            .first()
        )
        if not assn:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
        record(self.db, 'STAFF_REMOVED', gym_id, owner_user_id, user_id=user_id)
        publish(self.db, user_id, 'STAFF_REMOVED', gym_id)
        self.db.delete(assn)
        self.db.commit()

    def staff_gym_ids(self, *, staff_user_id: int) -> list[int]:
        return list(
            self.db.execute(select(GymStaffAssignment.gym_id).where(GymStaffAssignment.user_id == staff_user_id)).scalars().all()
        )
