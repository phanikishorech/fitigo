from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.gym import Gym, GymStatusHistory


class AdminGymService:
    def __init__(self, db: Session):
        self.db = db

    def list_pending(self) -> list[Gym]:
        stmt = select(Gym).where(Gym.status == "PENDING_APPROVAL").order_by(Gym.id.asc())
        return list(self.db.execute(stmt).scalars().all())

    def _change_status(self, *, gym: Gym, new_status: str, changed_by_user_id: int, reason: str | None = None) -> Gym:
        old = gym.status
        gym.status = new_status
        self.db.add(
            GymStatusHistory(
                gym_id=gym.id,
                old_status=old,
                new_status=new_status,
                changed_by_user_id=changed_by_user_id,
                reason=reason,
            )
        )
        self.db.commit()
        self.db.refresh(gym)
        return gym

    def approve(self, *, gym_id: int, changed_by_user_id: int) -> Gym:
        gym = self.db.execute(select(Gym).where(Gym.id == gym_id)).scalars().first()
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")
        if gym.status != "PENDING_APPROVAL":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Gym is not pending approval")
        gym.is_active = True
        return self._change_status(gym=gym, new_status="APPROVED", changed_by_user_id=changed_by_user_id)

    def reject(self, *, gym_id: int, changed_by_user_id: int, reason: str) -> Gym:
        gym = self.db.execute(select(Gym).where(Gym.id == gym_id)).scalars().first()
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")
        if gym.status != "PENDING_APPROVAL":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Gym is not pending approval")
        gym.is_active = False
        return self._change_status(gym=gym, new_status="REJECTED", changed_by_user_id=changed_by_user_id, reason=reason)

    def suspend(self, *, gym_id: int, changed_by_user_id: int, reason: str) -> Gym:
        gym = self.db.execute(select(Gym).where(Gym.id == gym_id)).scalars().first()
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")
        if gym.status not in {"APPROVED", "PENDING_APPROVAL"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Gym cannot be suspended")
        gym.is_active = False
        return self._change_status(gym=gym, new_status="SUSPENDED", changed_by_user_id=changed_by_user_id, reason=reason)

    def reactivate(self, *, gym_id: int, changed_by_user_id: int) -> Gym:
        gym = self.db.execute(select(Gym).where(Gym.id == gym_id)).scalars().first()
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")
        if gym.status != "SUSPENDED":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Gym is not suspended")
        gym.is_active = True
        return self._change_status(gym=gym, new_status="APPROVED", changed_by_user_id=changed_by_user_id)
