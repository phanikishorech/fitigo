"""Real route/policy tests in disposable SQLite. No live identities or gateway calls."""
from datetime import datetime, timedelta, timezone
import secrets

import pytest
from jose import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.models.auth import Role, User, UserRole
from app.models.booking import Booking
from app.models.cart import CartItem
from app.models.gym import Gym
from app.models.membership import GymMembershipPlan, UserMembership
from app.models.wallet import WalletTransaction
from app.routers import admin, auth, customer_access, gym_owner, gym_staff, gyms_public, memberships, notifications, users, wallet
from test_booking_access_qr import api as booking_api, create, qr, NOW

PASSWORD = 'Isolated fixture password 749!'


@pytest.fixture
def api(booking_api):
    client, headers, engine = booking_api
    for module in (admin, auth, customer_access, gym_owner, gym_staff, gyms_public, memberships, notifications, users, wallet):
        client.app.include_router(module.router, prefix='/api/v1')
    with Session(engine) as db:
        # Deliberately seed the old demo email ONLY in the isolated fixture so
        # a regression cannot hide behind its absence from the working DB.
        db.get(User, 1).email = 'customer@example.com'
        password_hash = hash_password(PASSWORD)
        for uid in range(1, 6):
            db.get(User, uid).password_hash = password_hash
            if uid != 1:
                db.get(User, uid).email = f'qr-{uid}@example.com'
        for uid, role_name in ((6, 'ADMIN'), (7, 'SUPER_ADMIN')):
            role = Role(name=role_name); db.add(role); db.flush()
            db.add(User(id=uid, email=f'qr-{uid}@example.com', password_hash=password_hash, status='ACTIVE'))
            db.flush(); db.add(UserRole(user_id=uid, role_id=role.id))
            headers[uid] = {'Authorization': f'Bearer {create_access_token(str(uid))}'}
        db.add(GymMembershipPlan(id=1, gym_id=1, name='Security plan', duration_days=30, price=500))
        db.add(UserMembership(id=1, user_id=1, gym_id=1, plan_id=1, start_at=datetime.utcnow()-timedelta(days=1),
                              end_at=datetime.utcnow()+timedelta(days=30), paid_amount=500, payment_status='PAID'))
        db.add(CartItem(id=1, user_id=1, booking_type='GYM', gym_id=1, booking_date=NOW.date(),
                        member_count=1, price_per_person=100, total_price=100))
        db.add(WalletTransaction(account_id=1, user_id=1, direction='IN', txn_type='TOPUP', amount=100,
                                 currency='INR', reference='private-fixture-reference'))
        db.commit()
    return booking_api


@pytest.mark.parametrize('uid,path', [(1, '/api/v1/profile'), (2, '/api/v1/gym-owner/gyms'),
                                    (3, '/api/v1/gym-staff/gyms'), (4, '/api/v1/users/me'),
                                    (6, '/api/v1/admin/ping'), (7, '/api/v1/admin/ping')])
def test_valid_login_refresh_and_role_request(api, uid, path):
    client, _, _ = api
    email = 'customer@example.com' if uid == 1 else f'qr-{uid}@example.com'
    response = client.post('/api/v1/auth/login', json={'email': email, 'password': PASSWORD})
    assert response.status_code == 200
    session = response.json()
    headers = {'Authorization': 'Bearer ' + session['access_token']}
    assert client.get(path, headers=headers).status_code == 200
    assert client.get('/api/v1/auth/session', headers=headers).json()['user']['id'] == uid
    refreshed = client.post('/api/v1/auth/refresh', json={'refresh_token': session['refresh_token']})
    assert refreshed.status_code == 200
    assert client.get(path, headers={'Authorization': 'Bearer ' + refreshed.json()['access_token']}).status_code == 200
    assert client.post('/api/v1/auth/refresh', json={'refresh_token': session['refresh_token']}).status_code == 401


@pytest.mark.parametrize('case', ['missing', 'malformed', 'expired', 'signature', 'algorithm', 'no-exp', 'no-sub',
                                'bad-sub', 'big-sub', 'negative-sub', 'bad-exp', 'bad-version', 'wrong-type', 'revoked'])
def test_bad_access_and_refresh_credentials_are_401(api, case):
    client, _, _ = api
    payload = {'sub': '1', 'type': 'access', 'exp': int((datetime.now(timezone.utc)+timedelta(minutes=5)).timestamp())}
    if case == 'expired': payload['exp'] = 1
    if case == 'no-exp': payload.pop('exp')
    if case == 'no-sub': payload.pop('sub')
    if case == 'bad-sub': payload['sub'] = 'not-a-user-id'
    if case == 'big-sub': payload['sub'] = '9' * 100
    if case == 'negative-sub': payload['sub'] = '-1'
    if case == 'bad-exp': payload['exp'] = None
    if case == 'bad-version': payload['version'] = False
    if case == 'wrong-type': payload['type'] = 'refresh'
    if case == 'revoked': payload['version'] = 99
    key = secrets.token_urlsafe(64) if case == 'signature' else settings.jwt_secret.get_secret_value()
    algorithm = 'HS512' if case == 'algorithm' else settings.jwt_algorithm
    token = jwt.encode(payload, key, algorithm=algorithm)
    if case == 'malformed': token = 'not.a.valid-token'
    headers = {} if case == 'missing' else {'Authorization': 'Bearer ' + token}
    assert client.get('/api/v1/users/me', headers=headers).status_code == 401
    # Refresh uses the same strict parser, plus its persisted session check.
    assert client.post('/api/v1/auth/refresh', json={'refresh_token': token}).status_code == 401


@pytest.mark.parametrize('authorization', ['', 'Basic abc', 'Bearer', 'Bearer ', 'Bearer invalid'])
def test_optional_public_auth_rejects_supplied_invalid_header(api, authorization):
    client, _, _ = api
    assert client.get('/api/v1/gyms/1/booking-options', headers={'Authorization': authorization}).status_code == 401


@pytest.mark.parametrize('path', ['/profile', '/profile/membership', '/profile/activity', '/profile/favorites',
                                 '/profile/membership/pass', '/wallet/balance', '/wallet/transactions', '/cart/items'])
def test_demo_email_never_substitutes_anonymous_identity(api, path):
    client, _, _ = api
    assert client.get('/api/v1'+path).status_code == 401


def test_public_browsing_is_anonymous_but_purchase_requires_customer(api):
    client, headers, engine = api
    options = '/api/v1/gyms/1/booking-options'
    result = client.get(options)
    assert result.status_code == 200
    assert not any(item['membership_included'] for item in result.json()['available_access_types'])
    assert any(item['membership_included'] for item in client.get(options, headers=headers[1]).json()['available_access_types'])
    body = {'items': [{'access_type_id': 'GYM_WORKOUT', 'gym_slot_id': 1, 'slot_date': str(NOW.date()), 'quantity': 1}]}
    assert client.post('/api/v1/gyms/1/access-bookings', json=body).status_code == 401
    assert client.post('/api/v1/gyms/1/access-bookings', headers=headers[2], json=body).status_code == 403
    assert client.post('/api/v1/cart/checkout').status_code == 401
    with Session(engine) as db:
        assert db.scalar(select(func.count(Booking.id))) == 0


def test_customer_cannot_read_mutate_or_issue_other_customer_booking(api):
    booking = create(api, ['Authorized visitor'])
    client, headers, engine = api
    base = f"/api/v1/bookings/{booking['id']}"
    assert client.get(base, headers=headers[4]).status_code == 404
    for suffix, body in [('cancel', {}), ('qr', None), ('visitors', {'visitor_names': ['Changed visitor']}),
                         ('reschedule', {'gym_slot_id': 1, 'slot_date': str(NOW.date())})]:
        assert client.post(base+'/'+suffix, headers=headers[4], json=body).status_code == 404
    assert client.get(f"/api/v1/profile/bookings/{booking['id']}/review", headers=headers[4]).status_code == 404
    assert client.get('/api/v1/bookings/me?user_id=1', headers=headers[4]).json() == []
    with Session(engine) as db:
        assert db.get(Booking, booking['id']).status == 'CONFIRMED'


def test_customer_membership_wallet_cart_and_identity_are_scoped(api):
    client, headers, engine = api
    assert client.get('/api/v1/memberships/me?user_id=1', headers=headers[4]).json() == []
    assert client.get('/api/v1/memberships/me/1/pause', headers=headers[4]).status_code == 404
    assert client.post('/api/v1/memberships/me/1/cancel', headers=headers[4]).status_code == 404
    assert client.get('/api/v1/users/me?user_id=1', headers=headers[4]).json()['id'] == 4
    assert client.get('/api/v1/cart/items?user_id=1', headers=headers[4]).json() == []
    assert client.delete('/api/v1/cart/items/1', headers=headers[4]).status_code == 404
    own = client.get('/api/v1/wallet/transactions', headers=headers[1])
    other = client.get('/api/v1/wallet/transactions?user_id=1', headers=headers[4])
    assert own.status_code == other.status_code == 200
    assert len(own.json()['transactions']) == 1 and other.json()['transactions'] == []
    with Session(engine) as db:
        assert db.get(UserMembership, 1).status == 'ACTIVE'
        assert db.get(CartItem, 1).status == 'ACTIVE'


@pytest.mark.parametrize('suffix', ['', '/slots', '/membership-plans', '/staff', '/bookings'])
def test_owner_cannot_read_another_gym(api, suffix):
    client, headers, _ = api
    response = client.get('/api/v1/gym-owner/gyms/1'+suffix, headers=headers[5])
    assert response.status_code == 404
    own = client.get('/api/v1/gym-owner/gyms/1'+suffix, headers=headers[2])
    assert own.status_code == 200


def test_owner_mutations_and_analytics_do_not_accept_browser_owner_ids(api):
    client, headers, engine = api
    assert client.put('/api/v1/gym-owner/gyms/1', headers=headers[5], json={'name': 'Stolen gym', 'owner_user_id': 5}).status_code == 404
    assert client.put('/api/v1/gym-owner/membership-plans/1', headers=headers[5], json={'price': '1'}).status_code == 404
    for path in ['/analytics', '/analytics/bookings', '/analytics/transactions', '/analytics/attendance', '/dashboard/summary']:
        assert client.get('/api/v1/gym-owner'+path+'?gym_id=1&owner_user_id=2', headers=headers[5]).status_code == 404
    with Session(engine) as db:
        assert db.get(Gym, 1).owner_user_id == 2
        assert db.get(GymMembershipPlan, 1).price == 500


def test_staff_and_owner_booking_and_scanner_boundaries(api):
    client, headers, engine = api
    booking = create(api, ['Authorized visitor'])
    assert client.get('/api/v1/gym-staff/gyms/1/bookings', headers=headers[3]).status_code == 200
    assert client.get('/api/v1/gym-staff/gyms/2/bookings', headers=headers[3]).status_code == 404
    assert client.get('/api/v1/gym-owner/gyms', headers=headers[3]).status_code == 403
    assert client.get(f"/api/v1/gym-owner/bookings/{booking['id']}", headers=headers[5]).status_code == 404
    for action in ['cancel', 'mark-attended', 'mark-no-show']:
        assert client.post(f"/api/v1/gym-owner/bookings/{booking['id']}/{action}", headers=headers[5], json={}).status_code == 404
    token = qr(api, booking)[0]['qr_token']
    denied = client.post('/api/v1/checkins/validate', headers=headers[3], json={'gym_id': 2, 'qr_token': token})
    assert denied.status_code == 403 and denied.json()['detail']['code'] == 'GYM_NOT_ALLOWED'
    allowed = client.post('/api/v1/checkins/validate', headers=headers[3], json={'gym_id': 1, 'qr_token': token})
    assert allowed.status_code == 200 and allowed.json()['success']
    with Session(engine) as db:
        db.get(Booking, booking['id']).gym_id = 2; db.commit()
    for action in ['mark-attended', 'mark-no-show']:
        assert client.post(f"/api/v1/gym-staff/bookings/{booking['id']}/{action}", headers=headers[3], json={}).status_code == 404


@pytest.mark.parametrize('uid', [1, 2, 3, 4, 5])
def test_admin_permissions_are_not_taken_from_token_roles(api, uid):
    client, _, _ = api
    headers = {'Authorization': 'Bearer '+create_access_token(str(uid), {'role': 'ADMIN', 'roles': ['SUPER_ADMIN']})}
    for path in ['/admin/ping', '/admin/users', '/admin/dashboard/summary', '/notifications/pending']:
        assert client.get('/api/v1'+path, headers=headers).status_code == 403
        assert client.get('/api/v1'+path).status_code == 401
    assert client.post('/api/v1/admin/gyms/1/feature', headers=headers).status_code == 403


def test_booking_creation_ignores_forged_identity_and_price(api):
    client, headers, engine = api
    response = client.post('/api/v1/bookings', headers=headers[4], json={
        'gym_slot_id': 1, 'slot_date': str(NOW.date()), 'quantity': 1,
        'user_id': 1, 'gym_id': 2, 'unit_price': 0, 'total_price': 0, 'status': 'CONFIRMED'
    })
    assert response.status_code == 200
    with Session(engine) as db:
        row = db.get(Booking, response.json()['id'])
        assert row.user_id == 4 and row.gym_id == 1 and row.total_price == 100
        assert row.status == 'PENDING_PAYMENT'


def test_deleted_inactive_and_version_changed_users_cannot_use_optional_auth(api, caplog):
    client, headers, engine = api
    with Session(engine) as db:
        db.get(User, 1).token_version = 1
        db.get(User, 4).status = 'SUSPENDED'
        db.commit()
    assert client.get('/api/v1/gyms/1/booking-options', headers=headers[1]).status_code == 401
    assert client.get('/api/v1/gyms/1/booking-options', headers=headers[4]).status_code == 403
    token = create_access_token('999999')
    assert client.get('/api/v1/users/me', headers={'Authorization': 'Bearer '+token}).status_code == 401
    assert token not in caplog.text and settings.jwt_secret.get_secret_value() not in caplog.text