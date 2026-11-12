"""Disposable SQLite + captured test transports; never sends real account messages."""
import re
from datetime import timedelta

import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, verify_password
from app.models.auth import AccountOtp, AuthRateLimit, PasswordResetToken, User
from app.models.staff import GymStaffAssignment, StaffInvitation
from app.models.gym import Gym
from app.repositories.user_repository import UserRepository
from app.services import account_delivery, otp_service, password_service
from app.services.password_service import digest, now
from test_security_boundaries import api as security_api, booking_api, PASSWORD


@pytest.fixture
def api(security_api, monkeypatch):
    mail, sms = [], []
    monkeypatch.setattr(settings, 'smtp_host', 'smtp.fixture.test')
    monkeypatch.setattr(settings, 'smtp_from', 'no-reply@example.com')
    monkeypatch.setattr(settings, 'public_frontend_url', 'https://app.example.test')
    monkeypatch.setattr(settings, 'sms_provider', 'twilio')
    monkeypatch.setattr(settings, 'twilio_account_sid', 'AC'+'1'*32)
    monkeypatch.setattr(settings, 'twilio_auth_token', SecretStr('isolated-provider-credential'))
    monkeypatch.setattr(settings, 'twilio_from_number', '+12025550123')
    monkeypatch.setattr(account_delivery, 'send_email', lambda address, subject, body: mail.append((address, subject, body)))
    monkeypatch.setattr(account_delivery, 'send_sms', lambda address, body: sms.append((address, body)))
    return (*security_api, mail, sms)


def invite(api, email='new-staff@example.com', owner=2, gym=1):
    return api[0].post(f'/api/v1/gym-owner/gyms/{gym}/staff/invite', headers=api[1][owner],
                      json={'email': email, 'first_name': 'New', 'last_name': 'Staff'})


def token(api):
    return re.search(r'#token=([A-Za-z0-9_-]+)', api[3][-1][2]).group(1)


def accept(api, value, **body):
    return api[0].post('/api/v1/auth/staff-invitations/accept', json={'token': value, **body})


def clear_limits(api):
    with Session(api[2]) as db:
        for row in db.scalars(select(AuthRateLimit)):
            row.window_start = now()-timedelta(days=1)
        db.commit()


def test_invite_accept_login_only_assigned_gym_and_no_secret_response(api):
    response = invite(api)
    assert response.status_code == 200
    value = token(api)
    assert value not in response.text and 'password' not in response.text
    with Session(api[2]) as db:
        user = db.scalar(select(User).where(User.email == 'new-staff@example.com'))
        uid = user.id
        assert user.status == 'PENDING_INVITATION'
        assert UserRepository(db).get_role_names(uid) == []
        assert db.scalar(select(func.count(GymStaffAssignment.id)).where(GymStaffAssignment.user_id == uid)) == 0
        assert db.scalar(select(StaffInvitation.token_hash)) == digest(value)
    inspected = api[0].post('/api/v1/auth/staff-invitations/inspect', json={'token': value})
    assert inspected.status_code == 200 and not inspected.json()['requires_current_password']
    assert accept(api, value, new_password=PASSWORD).status_code == 200
    assert accept(api, value, new_password=PASSWORD).status_code == 400
    login = api[0].post('/api/v1/auth/login', json={'email': 'new-staff@example.com', 'password': PASSWORD})
    assert login.status_code == 200 and login.json()['roles'] == ['GYM_STAFF']
    headers = {'Authorization': 'Bearer '+login.json()['access_token']}
    assert [g['id'] for g in api[0].get('/api/v1/gym-staff/gyms', headers=headers).json()] == [1]
    assert api[0].get('/api/v1/gym-staff/gyms/2/bookings', headers=headers).status_code == 404
    assert api[0].get('/api/v1/admin/ping', headers=headers).status_code == 403


def test_invitation_existing_account_requires_current_password_and_preserves_other_roles(api):
    assert invite(api, 'qr-4@example.com').status_code == 200
    value = token(api)
    assert accept(api, value, new_password='Attacker-chosen-password').status_code == 400
    assert accept(api, value, current_password=PASSWORD, new_password='Ignored-password-value').status_code == 200
    with Session(api[2]) as db:
        assert verify_password(PASSWORD, db.get(User, 4).password_hash)
        assert set(UserRepository(db).get_role_names(4)) == {'CUSTOMER', 'GYM_STAFF'}


def test_invitation_scope_payload_expiry_resend_and_revoke(api):
    assert invite(api, owner=5).status_code == 404
    assert not api[3]
    first = invite(api); assert first.status_code == 200
    old = token(api)
    assert accept(api, old, new_password=PASSWORD, gym_id=2, role='ADMIN').status_code == 422
    assert invite(api).status_code == 429
    with Session(api[2]) as db:
        db.scalar(select(StaffInvitation)).expires_at = now()-timedelta(seconds=1); db.commit()
    assert accept(api, old, new_password=PASSWORD).status_code == 400
    clear_limits(api)
    assert invite(api).status_code == 200
    replacement = token(api)
    assert replacement != old and accept(api, old, new_password=PASSWORD).status_code == 400
    path = '/api/v1/gym-owner/gyms/1/staff/invitations'
    assert api[0].get(path, headers=api[1][5]).status_code == 404
    rows = api[0].get(path, headers=api[1][2]).json()
    assert len(rows) == 1 and replacement not in str(rows)
    assert api[0].delete(path+'/'+rows[0]['id'], headers=api[1][2]).status_code == 200
    assert accept(api, replacement, new_password=PASSWORD).status_code == 400


@pytest.mark.parametrize('failure', ['configuration', 'provider'])
def test_invitation_failure_never_creates_access_or_claims_sent(api, monkeypatch, failure):
    if failure == 'configuration': monkeypatch.setattr(settings, 'smtp_host', None)
    else:
        def failed(*args): raise account_delivery.unavailable(True)
        monkeypatch.setattr(account_delivery, 'send_email', failed)
    response = invite(api)
    assert response.status_code == 503
    with Session(api[2]) as db:
        assert db.scalar(select(User).where(User.email == 'new-staff@example.com')) is None
        assert db.scalar(select(func.count(StaffInvitation.id))) == 0


def test_pending_invitation_cannot_be_activated_through_otp_or_password_reset(api):
    assert invite(api).status_code == 200
    address = 'new-staff@example.com'
    assert api[0].post('/api/v1/auth/email/send-otp', json={'email': address}).status_code == 200
    code = re.search(r'\b[0-9]{6}\b', api[3][-1][2]).group()
    assert api[0].post('/api/v1/auth/email/verify-otp', json={'email': address, 'otp': code}).status_code == 400
    assert api[0].post('/api/v1/auth/forgot-password', json={'email': address}).status_code == 200
    assert api[0].post('/api/v1/auth/reset-password', json={'token': token(api), 'new_password': PASSWORD}).status_code == 400


@pytest.mark.parametrize('channel', ['email', 'mobile'])
def test_otp_delivery_success_one_time_role_binding_and_resend_cooldown(api, channel):
    body = {'email': 'customer@example.com'} if channel == 'email' else {'country_code': '+1', 'mobile_number': '2025550199'}
    url = '/api/v1/auth/'+channel
    response = api[0].post(url+'/send-otp', json=body)
    assert response.status_code == 200 and response.json()['delivery_status'] == 'PROVIDER_ACCEPTED'
    message = api[3][-1][2] if channel == 'email' else api[4][-1][1]
    code = re.search(r'\b[0-9]{6}\b', message).group()
    assert code not in response.text
    assert api[0].post(url+'/send-otp', json=body).status_code == 429
    with Session(api[2]) as db:
        row = db.scalar(select(AccountOtp)); assert row.code_hash != code and row.purpose == 'LOGIN'
    response = api[0].post(url+'/verify-otp', json={**body, 'otp': code})
    assert response.status_code == 200 and response.json()['roles'] == ['CUSTOMER']
    identity = api[0].get('/api/v1/auth/session', headers={'Authorization': 'Bearer '+response.json()['access_token']})
    assert identity.status_code == 200
    assert identity.json()['user']['is_email_verified' if channel == 'email' else 'is_phone_verified']
    assert api[0].post(url+'/verify-otp', json={**body, 'otp': code}).status_code == 400


@pytest.mark.parametrize('condition', ['expired', 'attempts', 'version', 'contact', 'purpose'])
def test_otp_expiry_bruteforce_and_account_binding(api, condition):
    body = {'email': 'customer@example.com'}
    assert api[0].post('/api/v1/auth/email/send-otp', json=body).status_code == 200
    code = re.search(r'\b[0-9]{6}\b', api[3][-1][2]).group()
    if condition == 'attempts':
        wrong = '000000' if code != '000000' else '111111'
        for _ in range(settings.otp_max_attempts):
            assert api[0].post('/api/v1/auth/email/verify-otp', json={**body, 'otp': wrong}).status_code == 400
    else:
        with Session(api[2]) as db:
            row = db.scalar(select(AccountOtp))
            if condition == 'expired': row.expires_at = now()-timedelta(seconds=1)
            if condition == 'version': db.get(User, 1).token_version += 1
            if condition == 'contact': db.get(User, 1).email = 'changed@example.com'
            if condition == 'purpose': row.purpose = 'RECOVERY'
            db.commit()
    assert api[0].post('/api/v1/auth/email/verify-otp', json={**body, 'otp': code}).status_code == 400


def test_otp_failed_transport_not_successful_and_resend_invalidates_old_code(api, monkeypatch):
    body = {'email': 'customer@example.com'}
    codes = iter(['123456', '654321'])
    monkeypatch.setattr(otp_service.OtpService, '_generate_otp', lambda self: next(codes))
    assert api[0].post('/api/v1/auth/email/send-otp', json=body).status_code == 200
    clear_limits(api)
    assert api[0].post('/api/v1/auth/email/send-otp', json=body).status_code == 200
    assert api[0].post('/api/v1/auth/email/verify-otp', json={**body, 'otp': '123456'}).status_code == 400
    assert api[0].post('/api/v1/auth/email/verify-otp', json={**body, 'otp': '654321'}).status_code == 200
    clear_limits(api)
    monkeypatch.setattr(otp_service.OtpService, '_generate_otp', lambda self: '222222')
    def failed(*args): raise RuntimeError('PRIVATE PROVIDER BODY')
    monkeypatch.setattr(account_delivery, 'send_email', failed)
    response = api[0].post('/api/v1/auth/email/send-otp', json=body)
    assert response.status_code == 503 and 'PRIVATE' not in response.text
    assert api[0].post('/api/v1/auth/email/verify-otp', json={**body, 'otp': '222222'}).status_code == 400


def test_recovery_provider_failure_is_non_enumerating_and_expiry_configurable(api, monkeypatch):
    monkeypatch.setattr(settings, 'password_reset_expiry_minutes', 5)
    start = now()
    assert api[0].post('/api/v1/auth/forgot-password', json={'email': 'customer@example.com'}).status_code == 200
    value = token(api)
    with Session(api[2]) as db:
        row = db.scalar(select(PasswordResetToken))
        assert 299 <= (password_service.as_utc(row.expires_at)-start).total_seconds() <= 305
    def failed(*args): raise account_delivery.unavailable(True)
    monkeypatch.setattr(account_delivery, 'send_email', failed)
    a = api[0].post('/api/v1/auth/forgot-password', json={'email': 'customer@example.com'})
    b = api[0].post('/api/v1/auth/forgot-password', json={'email': 'unknown@example.com'})
    assert a.status_code == b.status_code == 503 and a.json() == b.json()
    old = create_access_token('1')
    assert api[0].post('/api/v1/auth/reset-password', json={'token': value, 'new_password': 'Changed password 123!'}).status_code == 200
    assert api[0].get('/api/v1/users/me', headers={'Authorization': 'Bearer '+old}).status_code == 401


def test_invitation_owner_transfer_and_wrong_token_cannot_grant_access(api):
    assert invite(api).status_code == 200
    value = token(api)
    assert accept(api, 'x'*43, new_password=PASSWORD).status_code == 400
    with Session(api[2]) as db:
        db.get(Gym, 1).owner_user_id = 5; db.commit()
    assert accept(api, value, new_password=PASSWORD).status_code == 400


def test_existing_invitation_password_bruteforce_is_limited(api):
    assert invite(api, 'qr-4@example.com').status_code == 200
    value = token(api)
    for _ in range(5): assert accept(api, value, current_password='wrong').status_code == 400
    assert accept(api, value, current_password=PASSWORD).status_code == 429


def test_sms_configuration_failure_is_explicit(api, monkeypatch):
    monkeypatch.setattr(settings, 'sms_provider', 'disabled')
    response = api[0].post('/api/v1/auth/mobile/send-otp', json={'country_code': '+1', 'mobile_number': '2025550199'})
    assert response.status_code == 503 and api[4] == []


def test_otp_code_cannot_be_used_for_another_identifier(api):
    assert api[0].post('/api/v1/auth/email/send-otp', json={'email': 'customer@example.com'}).status_code == 200
    code = re.search(r'\b[0-9]{6}\b', api[3][-1][2]).group()
    assert api[0].post('/api/v1/auth/email/verify-otp', json={'email': 'qr-4@example.com', 'otp': code}).status_code == 400