"""Direct My Access contract checks in disposable SQLite; no live records."""
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_platform_memberships import api
from test_membership_pause import pause_api, NOW
from app.models.access import AccessQrToken
from app.models.gym import Gym
from app.models.membership import UserMembership
from app.services.access_service import AccessService


@pytest.mark.parametrize('identity,uid,scope', [(1, 2, 'MULTI_GYM'), (3, 4, 'SINGLE_GYM')])
def test_direct_daily_qr_uses_backend_scope_and_one_daily_checkin(pause_api, identity, uid, scope):
    client, headers, engine = pause_api
    calendar = client.get('/api/v1/customer/access-calendar?year=2026&month=10', headers=headers[identity])
    assert calendar.status_code == 200
    assert calendar.json()['access_type'] == scope
    with Session(engine) as db:
        assert db.scalar(select(func.count(AccessQrToken.id))) == 0
    # Deliberately no gym selection in the issuance request.
    response = client.get('/api/v1/customer/access/today', headers=headers[identity])
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    qr = response.json()
    assert qr['status'] == 'ACTIVE' and qr['access_type'] == scope
    assert qr['qr_token'].startswith('GYMACCESS:') and qr['expires_at']
    assert qr['gym'] == ({'id': 1, 'name': 'Pause gym 0'} if scope == 'SINGLE_GYM' else None)
    with Session(engine) as db:
        svc = AccessService(db)
        if scope == 'SINGLE_GYM':
            with pytest.raises(HTTPException):
                svc.validate_checkin(gym_id=2, qr_token=qr['qr_token'])
            chosen = 1
        else:
            nonpartner = Gym(owner_user_id=3, name='Not eligible', status='APPROVED', is_active=True, multi_gym_enabled=False)
            db.add(nonpartner); db.commit()
            with pytest.raises(HTTPException):
                svc.validate_checkin(gym_id=nonpartner.id, qr_token=qr['qr_token'])
            chosen = 2
        assert svc.validate_checkin(gym_id=chosen, qr_token=qr['qr_token'])['success']
        with pytest.raises(HTTPException):
            svc.validate_checkin(gym_id=1 if chosen == 2 else 2, qr_token=qr['qr_token'])
    assert client.get('/api/v1/customer/access/today', headers=headers[identity]).json()['status'] == 'USED'
    day = next(d for d in client.get('/api/v1/customer/access-calendar?year=2026&month=10', headers=headers[identity]).json()['days'] if d['status'] == 'TODAY')
    assert day['qr_status'] == 'USED' and not day['qr_available']


@pytest.mark.parametrize('change', ['expired', 'cancelled'])
def test_direct_qr_rejects_expired_or_inactive_membership(pause_api, change):
    client, headers, engine = pause_api
    with Session(engine) as db:
        membership = db.get(UserMembership, 1)
        if change == 'expired':
            membership.end_at = NOW - timedelta(seconds=1)
        else:
            membership.status = 'CANCELLED'
        db.commit()
    response = client.get('/api/v1/customer/access/today', headers=headers[1])
    assert response.status_code == 200 and response.json()['status'] == 'NO_ACCESS'
    with Session(engine) as db:
        assert db.scalar(select(func.count(AccessQrToken.id))) == 0