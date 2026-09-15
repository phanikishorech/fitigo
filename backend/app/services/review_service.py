from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus
from app.models.gym import Gym
from app.models.review import GymReview, ReviewStatus


class ReviewService:
    def __init__(self, db: Session):
        self.db = db

    def create_review(self, *, user_id: int, gym_id: int, rating: int, comment: str | None) -> GymReview:
        gym = self.db.execute(select(Gym).where(Gym.id == gym_id, Gym.status == "APPROVED", Gym.is_active.is_(True))).scalars().first()
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

        # Ensure user has at least one COMPLETED/VERIFIED visit in this gym.
        # A visit is considered completed only after the gym marks attendance as ATTENDED.
        has_completed_visit = (
            self.db.execute(
                select(Booking.id)
                .where(
                    Booking.user_id == user_id,
                    Booking.gym_id == gym_id,
                    Booking.status == BookingStatus.CONFIRMED.value,
                    Booking.attendance_status == "ATTENDED",
                )
                .limit(1)
            ).first()
            is not None
        )
        if not has_completed_visit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You can review only after your visit is completed (attendance verified)",
            )

        existing = (
            self.db.execute(select(GymReview).where(GymReview.user_id == user_id, GymReview.gym_id == gym_id)).scalars().first()
        )
        if existing:
            existing.rating = rating
            existing.comment = comment
            existing.status = ReviewStatus.PUBLISHED.value
            self.db.commit()
            self.db.refresh(existing)
            return existing

        review = GymReview(
            user_id=user_id,
            gym_id=gym_id,
            rating=rating,
            comment=comment,
            status=ReviewStatus.PUBLISHED.value,
        )
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)
        return review

    def list_public_reviews(self, *, gym_id: int, limit: int = 20, offset: int = 0) -> list[GymReview]:
        stmt = (
            select(GymReview)
            .where(GymReview.gym_id == gym_id, GymReview.status == ReviewStatus.PUBLISHED.value)
            .order_by(GymReview.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.execute(stmt).scalars().all())

    def set_review_visibility(self, *, review_id: int, published: bool) -> GymReview:
        r = self.db.execute(select(GymReview).where(GymReview.id == review_id)).scalars().first()
        if not r:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
        r.status = ReviewStatus.PUBLISHED.value if published else ReviewStatus.HIDDEN.value
        self.db.commit()
        self.db.refresh(r)
        return r

    def get_gym_rating_summary(self, *, gym_id: int) -> tuple[float, int]:
        avg, cnt = (
            self.db.execute(
                select(func.avg(GymReview.rating), func.count(GymReview.id)).where(
                    GymReview.gym_id == gym_id, GymReview.status == ReviewStatus.PUBLISHED.value
                )
            )
            .first()
        )
        return float(avg or 0), int(cnt or 0)
