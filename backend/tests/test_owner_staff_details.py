"""Staff identity is visible only within an authenticated owner's gym scope."""
from datetime import datetime
import pytest
from sqlalchemy.orm import Session
from app.models.auth import User
from app.models.staff import GymStaffAssignment
from test_owner_dashboard_metrics import api


def seed(api):
    with Session(api[2]) as db:
        staff = db.get(User, 4)
        staff.first_name, staff.last_name = 'Kiran', 'Trainer'
        staff.email, staff.phone = 'kiran@example.com', '+919999999999'
        staff.password_hash = 'DO-NOT-RETURN-PASSWORD-HASH'
        db.add(GymStaffAssignment(id=1, gym_id=1, user_id=4, role='STAFF', created_at=datetime(2026, 10, 20, 10)))
        db.add(GymStaffAssignment(id=2, gym_id=2, user_id=4, role='STAFF'))
        db.add(GymStaffAssignment(id=3, gym_id=3, user_id=3, role='STAFF'))
        db.commit()


def test_owner_gets_identity_contact_status_and_assignment_date(api):
    seed(api)
    response = api[0].get('/api/v1/gym-owner/gyms/1/staff', headers=api[1][1])
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    assert response.json() == [{'id': 1, 'gym_id': 1, 'user_id': 4, 'role': 'STAFF',
        'first_name': 'Kiran', 'last_name': 'Trainer', 'email': 'kiran@example.com', 'phone': '+919999999999',
        'account_status': 'ACTIVE', 'assigned_at': '2026-10-20T15:30:00+05:30'}]
    for secret in ['password_hash', 'DO-NOT-RETURN', 'token_version', 'refresh_token', 'temp_password']:
        assert secret not in response.text


@pytest.mark.parametrize('gym_id', [3, 999])
def test_foreign_or_missing_gym_is_not_disclosed(api, gym_id):
    seed(api)
    response = api[0].get(f'/api/v1/gym-owner/gyms/{gym_id}/staff', headers=api[1][1])
    assert response.status_code == 404
    assert 'kiran@example.com' not in response.text


@pytest.mark.parametrize('actor', [3, 4])
def test_non_owner_cannot_read_staff_personal_details(api, actor):
    seed(api)
    assert api[0].get('/api/v1/gym-owner/gyms/1/staff', headers=api[1][actor]).status_code == 403
    assert api[0].get('/api/v1/gym-owner/gyms/1/staff').status_code == 401


def test_null_fields_inactive_account_and_empty_team_are_explicit(api):
    seed(api)
    with Session(api[2]) as db:
        staff = db.get(User, 4)
        staff.first_name = staff.last_name = staff.phone = None
        staff.status = 'INACTIVE'
        db.commit()
    row = api[0].get('/api/v1/gym-owner/gyms/1/staff', headers=api[1][1]).json()[0]
    assert row['first_name'] is None and row['phone'] is None and row['account_status'] == 'INACTIVE'
    assert api[0].delete('/api/v1/gym-owner/gyms/1/staff/4', headers=api[1][1]).status_code == 200
    assert api[0].get('/api/v1/gym-owner/gyms/1/staff', headers=api[1][1]).json() == []
    # Removing a gym assignment does not delete the account or other gym access.
    assert len(api[0].get('/api/v1/gym-owner/gyms/2/staff', headers=api[1][1]).json()) == 1
    with Session(api[2]) as db:
        assert db.get(User, 4) is not None


def test_legacy_missing_account_is_visible_and_removable(api):
    with Session(api[2]) as db:
        # SQLite fixture permits simulating orphaned legacy records without
        # disabling constraints or touching the application database.
        db.add(GymStaffAssignment(id=8, gym_id=1, user_id=999, role='STAFF'))
        db.commit()
    row = api[0].get('/api/v1/gym-owner/gyms/1/staff', headers=api[1][1]).json()[0]
    assert row['user_id'] == 999 and row['email'] is None and row['account_status'] is None
    assert api[0].delete('/api/v1/gym-owner/gyms/1/staff/999', headers=api[1][1]).status_code == 200