"""Strict MySQL query/index regression; runner-owned database, rolled-back fixtures."""
from uuid import uuid4
from sqlalchemy import inspect, select, text
from app.database.session import SessionLocal
from app.models.auth import User
from app.models.gym import Gym
from app.services.gym_discovery import discover


def test_migrated_mysql_geo_filter_and_owner_projection():
    with SessionLocal() as db:
        try:
            owner = User(email=f'geo-{uuid4().hex}@example.test', password_hash='unused', status='ACTIVE')
            db.add(owner); db.flush()
            tag = f'Geo-{uuid4().hex}'
            for lat, active in [('0.01', True), ('1', True), ('0', False), (None, True)]:
                db.add(Gym(owner_user_id=owner.id, name=tag, status='APPROVED', is_active=active,
                           latitude=lat, longitude='0' if lat is not None else None))
            db.flush()
            result = discover(db, None, search=tag, city=None, facilities=None, min_rating=None,
                              open_now=None, membership_access=None, sort_by='distance', latitude=0,
                              longitude=0, radius_km=5, page=1, page_size=12)
            assert result.total_count == 1
            assert 1 < result.gyms[0].distance_km < 1.2
            assert 'ix_gyms_discovery_geo' in {item['name'] for item in inspect(db.bind).get_indexes('gyms')}
            # EXPLAIN confirms the bounding-box predicate can use the composite index.
            plan = db.execute(text("EXPLAIN FORMAT=TRADITIONAL SELECT id FROM gyms FORCE INDEX (ix_gyms_discovery_geo) "
                                   "WHERE status='APPROVED' AND is_active=1 AND geo_latitude BETWEEN -0.05 AND 0.05 "
                                   "AND geo_longitude BETWEEN -0.05 AND 0.05")).mappings().first()
            assert plan['key'] == 'ix_gyms_discovery_geo'
            gym = db.scalar(select(Gym).where(Gym.id == result.gyms[0].gym_id))
            gym.latitude = '5'; db.flush()
            assert gym.geo_latitude == 5
        finally:
            db.rollback()