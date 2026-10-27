from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models.booking import Booking, Payment
from app.models.access import Checkin
from app.models.auth import User
from app.models.gym import Gym
from app.models.review import GymReview, ReviewStatus


def review_eligible():
    """A customer-owned individual purchase plus scanner proof, never a manual flag."""
    return and_(Booking.access_source == 'BOOKING_ACCESS', Booking.status == 'CONFIRMED',
        or_(Booking.attendance_status.is_(None), Booking.attendance_status != 'NO_SHOW'),
        exists(select(Payment.id).where(Payment.booking_id == Booking.id, Payment.status == 'PAID')),
        exists(select(Checkin.id).where(Checkin.booking_id == Booking.id, Checkin.gym_id == Booking.gym_id,
            Checkin.user_id == Booking.user_id, Checkin.access_source == 'BOOKING_ACCESS', Checkin.status == 'SUCCESS')))


class ReviewService:
    def __init__(self, db: Session):
        self.db = db

    def create_review(self, *, user_id: int, gym_id: int, rating: int, comment: str | None, booking_id: int | None = None) -> GymReview:
        if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
            raise HTTPException(422, 'Rating must be an integer from 1 to 5.')
        comment = comment.strip() if comment else None
        if comment and len(comment) > 2000:
            raise HTTPException(422, 'Feedback must be at most 2,000 characters.')
        user = self.db.scalar(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True))
        if not user or user.status != 'ACTIVE':
            raise HTTPException(403, 'Account unavailable')
        gym = self.db.execute(select(Gym).where(Gym.id == gym_id, Gym.status == "APPROVED", Gym.is_active.is_(True))).scalars().first()
        if not gym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

        # Recheck server-side on every submit, including callers of the original
        # gym review endpoint that do not provide a booking ID.
        has_completed_visit = (
            self.db.execute(
                select(Booking.id)
                .where(
                    Booking.user_id == user_id,
                    Booking.gym_id == gym_id,
                    review_eligible(),
                    Booking.id == booking_id if booking_id is not None else True,
                )
                .limit(1)
                .with_for_update()
            ).first()
            is not None
        )
        if not has_completed_visit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You can review only after a paid individual booking has a successful check-in.",
            )

        existing = (
            self.db.execute(select(GymReview).where(GymReview.user_id == user_id, GymReview.gym_id == gym_id)).scalars().first()
        )
        if existing:
            existing.rating = rating
            existing.comment = comment
            # Customer edits cannot override an administrator's visibility decision.
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

    def booking_review(self, *, user_id: int, booking_id: int):
        row = self.db.execute(select(Booking, Gym, review_eligible().label('eligible'))
            .join(Gym, Gym.id == Booking.gym_id).where(Booking.id == booking_id, Booking.user_id == user_id)).first()
        if not row:
            raise HTTPException(404, 'Booking not found')
        booking, gym, eligible = row
        review = self.db.scalar(select(GymReview).where(GymReview.user_id == user_id, GymReview.gym_id == gym.id))
        can_submit = bool(eligible and gym.status == 'APPROVED' and gym.is_active)
        return {'booking_id': booking.id, 'gym_id': gym.id, 'gym_name': gym.name,
            'can_review': can_submit, 'reason': None if can_submit else 'Feedback is available after a paid individual booking has a successful check-in at an available gym.',
            'review': {'id': review.id, 'rating': review.rating, 'comment': review.comment, 'status': review.status} if review else None}

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
