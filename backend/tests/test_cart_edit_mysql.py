"""Real InnoDB stale-edit serialization on runner-owned MySQL only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, time
from threading import Barrier
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select, func
from app.database.session import SessionLocal
from app.core.time import ist_today
from app.models.auth import User
from app.models.gym import Gym, GymOperatingHours
from app.models.cart import CartItem
from app.routers.cart import add_gym_to_cart, update_cart_item, cart_summary
from app.schemas.cart import CartItemCreateGymRequest, CartItemUpdateRequest


def test_same_version_concurrent_edits_only_one_saves_on_mysql():
    day = ist_today() + timedelta(days=2)
    with SessionLocal() as db:
        user = User(email=f'edit-{uuid4().hex}@example.test', password_hash='unused', status='ACTIVE')
        db.add(user); db.flush()
        gym = Gym(owner_user_id=user.id, name='Isolated edit fixture', status='APPROVED', is_active=True, gym_price_per_person=100)
        db.add(gym); db.flush()
        db.add(GymOperatingHours(gym_id=gym.id, day_of_week=day.weekday(), open_time=time(6), close_time=time(22), is_closed=False))
        db.commit(); uid, gid = user.id, gym.id
        item = add_gym_to_cart(CartItemCreateGymRequest(gym_id=gid, booking_date=day,
            preferred_start_time=time(14), member_count=1, visitor_names=['Original visitor']), db, user)
    barrier = Barrier(2)
    def save(name, hour):
        with SessionLocal() as db:
            actor = db.get(User, uid)
            barrier.wait(timeout=10)
            try:
                updated = update_cart_item(item.id, CartItemUpdateRequest(booking_type='GYM', gym_id=gid,
                    booking_date=day, preferred_start_time=time(hour), member_count=1, visitor_names=[name],
                    expected_updated_at=item.updated_at), db, actor)
                return 'saved', updated.visitor_names[0], updated.updated_at
            except HTTPException as error:
                db.rollback()
                assert error.status_code == 409
                return 'conflict', None, None
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(save, 'First visitor', 15), pool.submit(save, 'Second visitor', 16)
        results = [first.result(timeout=20), second.result(timeout=20)]
    assert sorted(result[0] for result in results) == ['conflict', 'saved']
    winner = next(result for result in results if result[0] == 'saved')
    with SessionLocal() as db:
        current = db.get(CartItem, item.id)
        assert current.visitor_names == [winner[1]]
        assert current.updated_at == winner[2] and current.updated_at != item.updated_at
        assert db.scalar(select(func.count(CartItem.id)).where(CartItem.user_id == uid)) == 1
        assert cart_summary(db, db.get(User, uid)) == {'count': 1}
        db.rollback()