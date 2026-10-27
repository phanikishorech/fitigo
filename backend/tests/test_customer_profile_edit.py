import pytest
from sqlalchemy.orm import Session
from app.core.security import hash_password
from app.models.auth import User
from app.routers import users
from test_booking_access_qr import api as booking_api


@pytest.fixture
def api(booking_api):
    client, headers, engine = booking_api
    client.app.include_router(users.router, prefix='/api/v1')
    with Session(engine) as db:
        for uid in (1, 2):
            db.get(User, uid).email = f'qr-{uid}@example.com'
        user = db.get(User, 1)
        user.password_hash = hash_password('Current-password1')
        user.is_email_verified, user.is_phone_verified = True, True
        db.commit()
    return client, headers, engine


def body(**values):
    return {'first_name': 'Updated', 'last_name': 'Customer', 'email': 'qr-1@example.com', 'phone': None, **values}


def test_name_update_preserves_session_and_verification(api):
    response = api[0].patch('/api/v1/users/me', headers=api[1][1], json=body())
    assert response.status_code == 200, response.text
    assert not response.json()['reauthenticate']
    assert response.json()['user']['first_name'] == 'Updated'
    assert response.json()['user']['is_email_verified']
    assert api[0].get('/api/v1/users/me', headers=api[1][1]).status_code == 200


def test_contact_requires_password_revokes_session_and_never_marks_verified(api):
    for password in [None, 'incorrect']:
        payload = body(email='new@example.com', **({'current_password': password} if password else {}))
        assert api[0].patch('/api/v1/users/me', headers=api[1][1], json=payload).status_code == 400
    response = api[0].patch('/api/v1/users/me', headers=api[1][1], json=body(email='new@example.com', phone='+919999999999', current_password='Current-password1'))
    assert response.status_code == 200, response.text
    assert response.json()['reauthenticate']
    assert not response.json()['user']['is_email_verified'] and not response.json()['user']['is_phone_verified']
    assert api[0].get('/api/v1/users/me', headers=api[1][1]).status_code == 401


def test_duplicate_and_privilege_edit_fail_without_partial_changes(api):
    assert api[0].patch('/api/v1/users/me', headers=api[1][1], json=body(email='qr-2@example.com', current_password='Current-password1')).status_code == 409
    for extra in [{'status': 'ADMIN'}, {'is_email_verified': True}, {'id': 2}, {'phone': 'bad'}, {'first_name': ' '}]:
        assert api[0].patch('/api/v1/users/me', headers=api[1][1], json=body(**extra)).status_code == 422
    assert api[0].patch('/api/v1/users/me', json=body()).status_code == 401
    with Session(api[2]) as db:
        assert db.get(User, 1).first_name != 'Updated'
        assert db.get(User, 2).email == 'qr-2@example.com'