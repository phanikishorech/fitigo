from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.gym import Gym, GymFacility, GymFacilityMapping, GymImage, GymOperatingHours


class GymRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_gym(self, gym: Gym) -> Gym:
        self.db.add(gym)
        self.db.flush()
        return gym

    def get_owner_gyms(self, owner_user_id: int) -> list[Gym]:
        stmt = select(Gym).where(Gym.owner_user_id == owner_user_id).order_by(Gym.id.desc())
        return list(self.db.execute(stmt).scalars().all())

    def get_gym_by_id(self, gym_id: int) -> Gym | None:
        stmt = select(Gym).where(Gym.id == gym_id)
        return self.db.execute(stmt).scalars().first()

    def get_owner_gym_by_id(self, *, owner_user_id: int, gym_id: int) -> Gym | None:
        stmt = select(Gym).where(Gym.id == gym_id, Gym.owner_user_id == owner_user_id)
        return self.db.execute(stmt).scalars().first()

    def add_image(self, image: GymImage) -> GymImage:
        self.db.add(image)
        self.db.flush()
        return image

    def list_facilities(self) -> list[GymFacility]:
        stmt = select(GymFacility).order_by(GymFacility.name.asc())
        return list(self.db.execute(stmt).scalars().all())

    def set_gym_facilities(self, *, gym_id: int, facility_ids: list[int]) -> None:
        # remove existing mappings and replace
        self.db.execute(delete(GymFacilityMapping).where(GymFacilityMapping.gym_id == gym_id))
        for fid in facility_ids:
            self.db.add(GymFacilityMapping(gym_id=gym_id, facility_id=fid))
        self.db.flush()

    def set_operating_hours(self, *, gym_id: int, items: list[GymOperatingHours]) -> None:
        self.db.execute(delete(GymOperatingHours).where(GymOperatingHours.gym_id == gym_id))
        for it in items:
            self.db.add(it)
        self.db.flush()
