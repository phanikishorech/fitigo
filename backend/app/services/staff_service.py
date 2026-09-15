from __future__ import annotations

import secrets

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.roles import ROLE_GYM_STAFF
from app.models.auth import User
from app.models.gym import Gym
from app.models.staff import GymStaffAssignment
from app.services.auth_service import AuthService


class StaffService:
    def __init__(self, db: Session):
        self.db = db

    def invite_staff(self, *, owner_user_id: int, gym_id: int, email: str, first_name: str | None, last_name: str | None) -> dict:
        gym = self.db.execute(select(Gym).where(Gym.id == gym_id, Gym.owner_user_id == owner_user_id)).scalars().first()
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

        auth = AuthService(self.db)
        staff = self.db.execute(select(User).where(User.email == email)).scalars().first()
        temp_password = None
        if not staff:
            temp_password = secrets.token_urlsafe(12)
            staff = auth.register_user(
                first_name=first_name or "Staff",
                last_name=last_name or "User",
                email=email,
                phone=None,
                password=temp_password,
                role_name=ROLE_GYM_STAFF,
            )
        else:
            # Ensure staff role exists
            role = auth.repo.get_or_create_role(ROLE_GYM_STAFF)
            current_roles = set(auth.repo.get_role_names(staff.id))
            if ROLE_GYM_STAFF not in current_roles:
                auth.repo.assign_role(staff.id, role.id)
                self.db.commit()

        existing = (
            self.db.execute(
                select(GymStaffAssignment).where(GymStaffAssignment.gym_id == gym_id, GymStaffAssignment.user_id == staff.id)
            )
            .scalars()
            .first()
        )
        if existing:
            return {"assignment_id": existing.id, "staff_user_id": staff.id, "temp_password": temp_password}

        assignment = GymStaffAssignment(gym_id=gym_id, user_id=staff.id, role="STAFF")
        self.db.add(assignment)
        self.db.commit()
        self.db.refresh(assignment)
        return {"assignment_id": assignment.id, "staff_user_id": staff.id, "temp_password": temp_password}

    def list_gym_staff(self, *, owner_user_id: int, gym_id: int) -> list[GymStaffAssignment]:
        gym = self.db.execute(select(Gym).where(Gym.id == gym_id, Gym.owner_user_id == owner_user_id)).scalars().first()
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")
        return list(self.db.execute(select(GymStaffAssignment).where(GymStaffAssignment.gym_id == gym_id)).scalars().all())

    def remove_staff(self, *, owner_user_id: int, gym_id: int, user_id: int) -> None:
        gym = self.db.execute(select(Gym).where(Gym.id == gym_id, Gym.owner_user_id == owner_user_id)).scalars().first()
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")
        assn = (
            self.db.execute(
                select(GymStaffAssignment).where(GymStaffAssignment.gym_id == gym_id, GymStaffAssignment.user_id == user_id)
            )
            .scalars()
            .first()
        )
        if not assn:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
        self.db.delete(assn)
        self.db.commit()

    def staff_gym_ids(self, *, staff_user_id: int) -> list[int]:
        return list(
            self.db.execute(select(GymStaffAssignment.gym_id).where(GymStaffAssignment.user_id == staff_user_id)).scalars().all()
        )
