"""Review query + concurrent upsert on disposable strict-mode MySQL."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import os
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.review import GymReview
from app.services.review_service import ReviewService
from test_owner_dashboard_mysql import mysql_api, booking, checkin, paid_booking, DAY, NOW
from app.core.time import stored_instant

pytestmark = pytest.mark.skipif(os.getenv('FITIGO_MYSQL_DASHBOARD_TESTS') != '1', reason='Disposable MySQL is opt-in')


def test_concurrent_rating_updates_keep_one_gym_review(mysql_api):
    _, _, engine = mysql_api
    with Session(engine) as db:
        row = booking(db, 1, day=DAY)
        paid_booking(db, row, 100, at=stored_instant(NOW))
        checkin(db, 1, booked=row, at=stored_instant(NOW))
        booking_id = row.id
        db.commit()
    barrier = Barrier(2)
    def submit(rating):
        with Session(engine) as db:
            barrier.wait(timeout=10)
            result = ReviewService(db).create_review(user_id=3, gym_id=1, booking_id=booking_id, rating=rating, comment='Concurrent test')
            return result.id
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(submit, [4, 5]))
    assert ids[0] == ids[1]
    with Session(engine) as db:
        assert db.scalar(select(func.count(GymReview.id))) == 1
        assert ReviewService(db).booking_review(user_id=3, booking_id=booking_id)['can_review']