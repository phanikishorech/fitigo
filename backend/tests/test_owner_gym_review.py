"""Owner review contract against disposable SQLite; no application data is modified."""
import pytest
from datetime import datetime
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Integer, MetaData, create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.database.base import Base
from app.database.session import get_db
from app.models.auth import Role, User, UserRole
from app.models.gym import Gym, GymStatusHistory
from app.routers.gym_owner import router
from app.schemas.gym import GymResponse


@pytest.fixture
def api():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    metadata = MetaData()
    for name in ('users', 'roles', 'user_roles', 'gyms', 'gym_status_history', 'gym_images', 'gym_facilities', 'gym_facility_mapping', 'gym_operating_hours'):
        table = Base.metadata.tables[name].to_metadata(metadata)
        table.c.id.type = Integer()
    metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Role(id=1, name='GYM_OWNER'))
        for uid in (1, 2):
            db.add(User(id=uid, email=f'owner-{uid}@example.test', password_hash='unused', status='ACTIVE'))
            db.add(UserRole(user_id=uid, role_id=1))
        for uid, role_name in ((3, 'ADMIN'), (4, 'SUPER_ADMIN'), (5, 'CUSTOMER')):
            db.add(Role(id=uid, name=role_name))
            db.add(User(id=uid, email=f'review-{uid}@example.test', password_hash='unused', status='ACTIVE'))
            db.add(UserRole(user_id=uid, role_id=uid))
        db.add(Gym(id=1, owner_user_id=1, name='Review fixture', status='REJECTED', is_active=False))
        for hid, reason in ((1, 'Old reason'), (2, 'Please update your address.')):
            db.add(GymStatusHistory(id=hid, gym_id=1, old_status='PENDING_APPROVAL', new_status='REJECTED', changed_by_user_id=2, reason=reason, created_at=datetime(2026, 9, 1)))
        db.commit()
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    from app.routers.admin import router as admin_router
    app.include_router(admin_router, prefix='/api/v1')
    def dependency():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = dependency
    with TestClient(app) as client:
        yield client, engine, {'Authorization': f'Bearer {create_access_token("1")}'}
    engine.dispose()


def test_latest_rejection_is_owner_only_and_edit_keeps_review_state(api):
    client, engine, headers = api
    response = client.get('/api/v1/gym-owner/gyms/1', headers=headers)
    assert response.status_code == 200
    assert response.json()['rejection_reason'] == 'Please update your address.'
    assert response.json()['can_submit_for_approval'] is True
    other = {'Authorization': f'Bearer {create_access_token("2")}'}
    assert client.get('/api/v1/gym-owner/gyms/1', headers=other).status_code == 404
    assert client.get('/api/v1/gym-owner/gyms/1').status_code == 401
    updated = client.put('/api/v1/gym-owner/gyms/1', headers=headers, json={'name': 'Updated fixture', 'address_line_1': 'Corrected address'})
    assert updated.status_code == 200
    assert updated.json()['status'] == 'REJECTED'
    assert updated.json()['rejection_reason'] == 'Please update your address.'
    assert 'rejection_reason' not in GymResponse.model_fields
    assert client.post('/api/v1/gym-owner/gyms/1/submit', headers=other).status_code == 404
    with Session(engine) as db:
        assert db.get(Gym, 1).status == 'REJECTED'


def test_resubmit_is_inactive_audited_and_cannot_be_repeated(api):
    client, engine, headers = api
    assert client.post('/api/v1/gym-owner/gyms/1/submit', headers=headers).json()['new_status'] == 'PENDING_APPROVAL'
    data = client.get('/api/v1/gym-owner/gyms/1', headers=headers).json()
    assert data['status'] == 'PENDING_APPROVAL'
    assert data['is_active'] is False
    assert data['can_submit_for_approval'] is False
    assert data['rejection_reason'] is None
    assert client.post('/api/v1/gym-owner/gyms/1/submit', headers=headers).status_code == 400
    with Session(engine) as db:
        history = db.scalars(select(GymStatusHistory).order_by(GymStatusHistory.id)).all()
        assert len(history) == 3
        assert history[1].reason == 'Please update your address.'
        assert history[2].old_status == 'REJECTED'
        assert history[2].new_status == 'PENDING_APPROVAL'
        assert history[2].changed_by_user_id == 1
        from app.services.admin_gym_service import AdminGymService
        approved = AdminGymService(db).approve(gym_id=1, changed_by_user_id=2)
        assert approved.status == 'APPROVED'
        assert approved.is_active is True


@pytest.mark.parametrize('status,allowed', [('DRAFT', True), ('PENDING_APPROVAL', False), ('APPROVED', False), ('SUSPENDED', False), ('INACTIVE', False)])
def test_capability_matches_existing_backend_transition(api, status, allowed):
    client, engine, headers = api
    with Session(engine) as db:
        db.get(Gym, 1).status = status
        db.commit()
    data = client.get('/api/v1/gym-owner/gyms/1', headers=headers).json()
    assert data['can_submit_for_approval'] is allowed
    assert data['rejection_reason'] is None
    response = client.post('/api/v1/gym-owner/gyms/1/submit', headers=headers)
    assert response.status_code == (200 if allowed else 400)
    if allowed:
        assert response.json()['new_status'] == 'PENDING_APPROVAL'


def test_missing_reason_never_falls_back_to_an_older_reason(api):
    client, engine, headers = api
    with Session(engine) as db:
        db.get(GymStatusHistory, 2).reason = None
        db.commit()
    assert client.get('/api/v1/gym-owner/gyms/1', headers=headers).json()['rejection_reason'] is None