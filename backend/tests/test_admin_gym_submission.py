"""Private admin submission data, role boundaries, and owner parity."""
from datetime import time
import pytest
from sqlalchemy.orm import Session
from app.core.security import create_access_token
from app.models.gym import Gym, GymImage, GymFacility, GymFacilityMapping, GymOperatingHours
from app.schemas.gym import GymResponse
from test_owner_gym_review import api


@pytest.mark.parametrize('role_id', [3, 4])
def test_admin_reads_complete_nonpublic_submission(api, role_id):
    client, engine, owner_headers = api
    with Session(engine) as db:
        gym = db.get(Gym, 1)
        gym.description = 'Submitted description'
        gym.address_line_1 = '42 Test Road'
        gym.city = 'Test City'
        gym.latitude = '17.4'
        gym.longitude = '78.4'
        gym.gym_price_per_person = 129
        db.add(GymImage(id=1, gym_id=1, file_path='gym/1/photo.webp', original_filename='Training floor', is_cover=True))
        db.add(GymFacility(id=1, name='Parking'))
        db.add(GymFacilityMapping(id=1, gym_id=1, facility_id=1))
        db.add(GymOperatingHours(id=1, gym_id=1, day_of_week=0, open_time=time(6), close_time=time(22), is_closed=False))
        db.add(GymOperatingHours(id=2, gym_id=1, day_of_week=6, is_closed=True))
        db.commit()
    headers = {'Authorization': f'Bearer {create_access_token(str(role_id))}'}
    response = client.get('/api/v1/admin/gyms/1', headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data['description'] == 'Submitted description'
    assert data['address_line_1'] == '42 Test Road'
    assert data['latitude'] == '17.4'
    assert data['longitude'] == '78.4'
    assert data['images'][0]['file_path'] == 'gym/1/photo.webp'
    assert data['facilities'][0]['name'] == 'Parking'
    assert data['operating_hours'][0]['open_time'] == '06:00:00'
    assert data['operating_hours'][1]['is_closed'] is True
    assert data['gym_price_per_person'] == '129.00'
    assert data['rejection_reason'] == 'Please update your address.'
    assert data['review_history'][0]['reason'] == data['rejection_reason']
    assert data['allowed_actions'] == []
    owner = client.get('/api/v1/gym-owner/gyms/1', headers=owner_headers).json()
    for field in GymResponse.model_fields:
        assert data[field] == owner[field], field
    assert 'review_history' not in owner
    with Session(engine) as db:
        assert db.get(Gym, 1).status == 'REJECTED'
        assert db.get(Gym, 1).is_active is False
    assert client.get('/api/v1/admin/gyms/999', headers=headers).status_code == 404


def test_detail_rejects_nonadmins_and_anonymous(api):
    client, _, _ = api
    assert client.get('/api/v1/admin/gyms/1').status_code == 401
    for uid in (1, 2, 5):
        assert client.get('/api/v1/admin/gyms/1', headers={'Authorization': f'Bearer {create_access_token(str(uid))}'}).status_code == 403


@pytest.mark.parametrize('status', ['DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'SUSPENDED', 'INACTIVE'])
def test_all_statuses_show_details_and_only_pending_can_be_reviewed(api, status):
    client, engine, _ = api
    with Session(engine) as db:
        db.get(Gym, 1).status = status
        db.commit()
    response = client.get('/api/v1/admin/gyms/1', headers={'Authorization': f'Bearer {create_access_token("3")}'} )
    assert response.status_code == 200
    data = response.json()
    assert data['images'] == []
    assert data['facilities'] == []
    assert data['operating_hours'] == []
    assert data['rejection_reason'] is None
    assert len(data['review_history']) == 2
    assert data['allowed_actions'] == (['APPROVE', 'REJECT'] if status == 'PENDING_APPROVAL' else [])