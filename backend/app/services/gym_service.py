from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, update

from app.models.gym import Gym, GymImage, GymOperatingHours
from app.repositories.gym_repository import GymRepository


class GymService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = GymRepository(db)

    def create_gym(self, *, owner_user_id: int, data: dict) -> Gym:
        # Normalize pricing fields
        if "gym_price_per_person" in data and data["gym_price_per_person"] is not None:
            data["gym_price_per_person"] = Decimal(str(data["gym_price_per_person"]))
        gym = Gym(owner_user_id=owner_user_id, **data)
        self.repo.create_gym(gym)
        self.db.commit()
        self.db.refresh(gym)
        return gym

    def update_gym(self, *, owner_user_id: int, gym_id: int, data: dict) -> Gym:
        gym = self.repo.get_owner_gym_by_id(owner_user_id=owner_user_id, gym_id=gym_id)
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

        for k, v in data.items():
            if v is not None:
                if k == "gym_price_per_person":
                    v = Decimal(str(v))
                setattr(gym, k, v)

        self.db.commit()
        self.db.refresh(gym)
        return gym

    def submit_for_approval(self, *, owner_user_id: int, gym_id: int) -> Gym:
        gym = self.repo.get_owner_gym_by_id(owner_user_id=owner_user_id, gym_id=gym_id)
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")
        if gym.status != "DRAFT":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Gym cannot be submitted")

        gym.status = "PENDING_APPROVAL"
        self.db.commit()
        self.db.refresh(gym)
        return gym

    def add_image(self, *, owner_user_id: int, gym_id: int, file_path: str, original_filename: str, content_type: str, is_cover: bool) -> GymImage:
        gym = self.repo.get_owner_gym_by_id(owner_user_id=owner_user_id, gym_id=gym_id)
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

        if is_cover:
            # Ensure only a single cover image exists.
            self.db.execute(update(GymImage).where(GymImage.gym_id == gym.id).values(is_cover=False))

        img = GymImage(
            gym_id=gym.id,
            file_path=file_path,
            original_filename=original_filename,
            image_type=content_type,
            is_cover=is_cover,
            display_order=0,
        )
        self.repo.add_image(img)
        self.db.commit()
        self.db.refresh(img)
        return img

    def set_cover_image(self, *, owner_user_id: int, gym_id: int, image_id: int) -> GymImage:
        gym = self.repo.get_owner_gym_by_id(owner_user_id=owner_user_id, gym_id=gym_id)
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

        img = self.db.execute(
            select(GymImage).where(GymImage.id == image_id, GymImage.gym_id == gym.id)
        ).scalars().first()
        if not img:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

        self.db.execute(update(GymImage).where(GymImage.gym_id == gym.id).values(is_cover=False))
        img.is_cover = True
        self.db.commit()
        self.db.refresh(img)
        return img

    def set_facilities(self, *, owner_user_id: int, gym_id: int, facility_ids: list[int]) -> None:
        gym = self.repo.get_owner_gym_by_id(owner_user_id=owner_user_id, gym_id=gym_id)
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")
        self.repo.set_gym_facilities(gym_id=gym.id, facility_ids=facility_ids)
        self.db.commit()

    def set_operating_hours(self, *, owner_user_id: int, gym_id: int, items: list[dict]) -> None:
        gym = self.repo.get_owner_gym_by_id(owner_user_id=owner_user_id, gym_id=gym_id)
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

        # Replace all for simplicity in MVP
        seen: set[int] = set()
        db_items: list[GymOperatingHours] = []
        for it in items:
            dow = int(it["day_of_week"])
            if dow in seen:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Duplicate day_of_week in operating hours",
                )
            seen.add(dow)

            is_closed = bool(it.get("is_closed", False))
            open_time = it.get("open_time")
            close_time = it.get("close_time")

            if is_closed:
                open_time = None
                close_time = None
            else:
                if open_time is None or close_time is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="open_time and close_time are required when is_closed=false",
                    )
                if close_time <= open_time:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="close_time must be after open_time",
                    )

            db_items.append(
                GymOperatingHours(
                    gym_id=gym.id,
                    day_of_week=dow,
                    open_time=open_time,
                    close_time=close_time,
                    is_closed=is_closed,
                )
            )

        self.repo.set_operating_hours(gym_id=gym.id, items=db_items)
        self.db.commit()
