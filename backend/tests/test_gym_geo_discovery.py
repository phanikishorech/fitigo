"""Synthetic coordinates are test fixtures only; no application records are changed."""
import math
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Integer, MetaData, create_engine, event, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.database.base import Base
from app.database.session import get_db
from app.models.gym import Gym
from app.models.auth import User
from app.routers.gyms_public import router
from app.services.gym_geo import coordinates, geographic_query


@pytest.fixture
def geo_api():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    @event.listens_for(engine, 'connect')
    def math_functions(connection, record):
        for name, fn, argc in [('radians', math.radians, 1), ('sin', math.sin, 1), ('cos', math.cos, 1),
                               ('asin', math.asin, 1), ('sqrt', math.sqrt, 1), ('pow', math.pow, 2)]:
            connection.create_function(name, argc, lambda *args, fn=fn: None if None in args else fn(*args))
    metadata = MetaData()
    for name in ('users', 'gyms', 'gym_images', 'gym_facilities', 'gym_facility_mapping', 'gym_operating_hours', 'gym_reviews', 'bookings', 'gym_slots'):
        Base.metadata.tables[name].to_metadata(metadata)
    # Copy remaining FK dependencies for this isolated model graph.
    for table in Base.metadata.sorted_tables:
        if table.name not in metadata.tables:
            table.to_metadata(metadata)
    for table in metadata.tables.values():
        if 'id' in table.c: table.c.id.type = Integer()
    metadata.create_all(engine)
    with Session(engine) as db:
        db.add(User(id=1, email='geo@example.test', password_hash='unused', status='ACTIVE'))
        for gid, km in enumerate([1, 7, 15, 35, 70], 1):
            db.add(Gym(id=gid, owner_user_id=1, name=f'Geo fixture {gid}', status='APPROVED', is_active=True,
                       latitude=str(km / 111.195), longitude='0', gym_price_per_person=100))
        for gid, status, active, lat in [(6, 'DRAFT', True, '0'), (7, 'APPROVED', False, '0'),
                                          (8, 'SUSPENDED', True, '0'), (9, 'APPROVED', True, 'invalid'),
                                          (10, 'APPROVED', True, '91'), (11, 'APPROVED', True, None)]:
            db.add(Gym(id=gid, owner_user_id=1, name=f'Hidden {gid}', status=status, is_active=active,
                       latitude=lat, longitude='0' if lat else None))
        db.commit()
    app = FastAPI(); app.include_router(router, prefix='/api/v1')
    def session():
        with Session(engine) as db: yield db
    app.dependency_overrides[get_db] = session
    with TestClient(app) as client: yield client, engine
    engine.dispose()


@pytest.mark.parametrize('radius,ids', [(5, [1]), (10, [1, 2]), (20, [1, 2, 3]), (50, [1, 2, 3, 4])])
def test_radii_visibility_and_real_distance(geo_api, radius, ids):
    response = geo_api[0].get(f'/api/v1/gyms/discover?latitude=0&longitude=0&radius_km={radius}&sort_by=distance')
    assert response.status_code == 200, response.text
    data = response.json()
    assert [g['gym_id'] for g in data['gyms']] == ids
    assert data['total_count'] == len(ids)
    assert data['gyms'][0]['distance_km'] == pytest.approx(1, abs=.001)
    assert data['gyms'][0]['starting_price'] == '100.00'
    assert all(g['is_active'] for g in data['gyms'])


@pytest.mark.parametrize('query', ['latitude=91&longitude=0', 'latitude=0&longitude=181', 'latitude=nan&longitude=0',
                                  'latitude=0', 'longitude=0', 'latitude=0&longitude=0&radius_km=0',
                                  'latitude=0&longitude=0&radius_km=201', 'page=0'])
def test_coordinate_and_radius_validation(geo_api, query):
    assert geo_api[0].get('/api/v1/gyms/discover?' + query).status_code == 422


def test_empty_and_pagination_without_capped_window(geo_api):
    client, engine = geo_api
    assert client.get('/api/v1/gyms/discover?latitude=60&longitude=60').json()['gyms'] == []
    with Session(engine) as db:
        db.add_all([Gym(owner_user_id=1, name=f'Bulk fixture {i}', status='APPROVED', is_active=True,
                        latitude='0', longitude='0') for i in range(705)])
        db.commit()
    data = client.get('/api/v1/gyms/discover?latitude=0&longitude=0&radius_km=5&page=12&page_size=60').json()
    assert data['total_count'] == 706
    assert len(data['gyms']) == 46
    assert data['has_more'] is False


def test_dateline_and_polar_bounds(geo_api):
    with Session(geo_api[1]) as db:
        db.add(Gym(id=12, owner_user_id=1, name='Dateline fixture', status='APPROVED', is_active=True, latitude='0', longitude='-179.99'))
        db.add(Gym(id=13, owner_user_id=1, name='Polar fixture', status='APPROVED', is_active=True, latitude='89.99', longitude='150'))
        db.commit()
        for lat, lon, target in [(0, 179.99, 12), (89.99, -30, 13)]:
            bounds, distance = geographic_query(Gym.geo_latitude, Gym.geo_longitude, lat, lon, 5)
            assert target in db.scalars(select(Gym.id).where(bounds, distance <= 5)).all()


def test_invalid_projection_and_index(geo_api):
    with Session(geo_api[1]) as db:
        assert db.get(Gym, 9).geo_latitude is None
        assert db.get(Gym, 10).geo_latitude is None
        assert coordinates('nan', '0') is None
        assert coordinates('0', '0') == (0, 0)
        indexes = db.execute(text("PRAGMA index_list('gyms')")).all()
        assert 'ix_gyms_discovery_geo' in [row[1] for row in indexes]


from test_owner_gym_review import api


def test_owner_updates_coordinates_with_authorization_and_validation(api):
    client, engine, headers = api
    payload = {'name': 'Owner coordinate fixture', 'latitude': '12.1', 'longitude': '77.2'}
    assert client.put('/api/v1/gym-owner/gyms/1', json=payload).status_code == 401
    assert client.put('/api/v1/gym-owner/gyms/1', headers=headers, json=payload).status_code == 200
    with Session(engine) as db:
        gym = db.get(Gym, 1)
        assert gym.geo_latitude == 12.1 and gym.geo_longitude == 77.2
    for latitude, longitude in [('91', '0'), ('nan', '0'), ('12', None), ('0', '-181')]:
        assert client.put('/api/v1/gym-owner/gyms/1', headers=headers, json={**payload, 'latitude': latitude, 'longitude': longitude}).status_code == 422
    assert client.put('/api/v1/gym-owner/gyms/1', headers=headers, json={'name': 'Unrelated update'}).status_code == 200
    with Session(engine) as db: assert db.get(Gym, 1).geo_latitude == 12.1