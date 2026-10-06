"""Isolated pause API/access tests. No configured database is mutated."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import Integer, MetaData, func, select, event
from sqlalchemy.orm import Session

from test_platform_memberships import api, create, plan_body
from app.models.membership import GymMembershipPlan, MembershipPause, UserMembership
from app.models.gym import Gym
from app.models.access import AccessQrToken, CustomerDailyAccess, Checkin
from app.services import membership_pause_service as pause_module, access_service
from app.services.membership_entitlement import active_memberships, included_ids
from app.services.membership_pause_service import MembershipPauseService
from app.services.membership_service import MembershipService
from app.services.access_service import AccessService

NOW = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)


@pytest.fixture
def pause_api(api, monkeypatch):
    client, headers, engine = api
    monkeypatch.setattr(pause_module, 'utcnow', lambda: NOW)
    monkeypatch.setattr(access_service, 'utcnow', lambda: NOW)
    monkeypatch.setattr(access_service, 'utc_today', lambda: NOW.date())
    from app.routers.gym_owner import router as owner_router
    from app.routers.customer_access import router as customer_router
    from app.routers.checkins import router as checkin_router
    client.app.include_router(owner_router, prefix='/api/v1')
    client.app.include_router(customer_router, prefix='/api/v1')
    client.app.include_router(checkin_router, prefix='/api/v1')
    platform = create(api, {'pause_rule': {'allowed': True, 'max_pause_days': 10}})
    with Session(engine) as db:
        gyms = [Gym(owner_user_id=3, name=f'Pause gym {i}', status='APPROVED', is_active=True, multi_gym_enabled=True) for i in range(2)]
        db.add_all(gyms); db.flush()
        plan = GymMembershipPlan(gym_id=gyms[0].id, name='Pause single plan', duration_days=30, price=Decimal('100'), pause_allowed=True, max_pause_days=10)
        db.add(plan); db.flush()
        db.add_all([
            UserMembership(user_id=2, gym_id=None, plan_id=None, membership_type='MULTI_GYM', platform_plan_id=platform['id'], status='ACTIVE', start_at=NOW-timedelta(hours=12), end_at=datetime(2026,11,1), original_end_at=datetime(2026,11,1), paid_amount=100, payment_status='PAID'),
            UserMembership(user_id=4, gym_id=gyms[0].id, plan_id=plan.id, status='ACTIVE', start_at=NOW-timedelta(hours=12), end_at=datetime(2026,11,1), paid_amount=100, payment_status='PAID'),
        ])
        db.commit()
    return api


def selection(start='2026-10-10', days=5):
    return {'start_date': start, 'days': days}


def preview(api, body=None, mid=1, user=1):
    return api[0].post(f'/api/v1/memberships/me/{mid}/pause/preview', headers=api[1][user], json=body or selection())


def confirm(api, body=None, mid=1, user=1, key='pause-test-request-1', token=None):
    body = body or selection()
    if token is None:
        result = preview(api, body, mid, user)
        assert result.status_code == 200, result.text
        token = result.json()['preview_token']
    return api[0].post(f'/api/v1/memberships/me/{mid}/pause', headers={**api[1][user], 'Idempotency-Key': key}, json={**body, 'accepted_preview':token})


def eligibility(api, mid=1, user=1):
    return api[0].get(f'/api/v1/memberships/me/{mid}/pause', headers=api[1][user])


def test_policy_preview_schedule_history_and_idempotency(pause_api):
    e = eligibility(pause_api).json()
    assert e['can_pause'] and e['pause_days_remaining'] == 10
    assert e['eligible_from'] == '2026-10-02' and e['eligible_until'] == '2026-10-31'
    p = preview(pause_api).json()
    assert p['end_date'] == '2026-10-14' and p['resumes_on'] == '2026-10-15'
    assert p['new_end_at'].startswith('2026-11-06')
    response = confirm(pause_api, token=p['preview_token'])
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved['membership_status'] == 'ACTIVE' and not saved['currently_paused']
    assert saved['pause_days_used'] == 5 and saved['pause_days_remaining'] == 5
    assert saved['history'][0]['status'] == 'SCHEDULED'
    assert saved['original_end_at'].startswith('2026-11-01')
    assert confirm(pause_api, token=p['preview_token']).json() == saved
    assert confirm(pause_api, selection(days=4), token=p['preview_token']).json()['detail']['code'] == 'IDEMPOTENCY_CONFLICT'
    with Session(pause_api[2]) as db:
        assert db.scalar(select(func.count(MembershipPause.id))) == 1
        assert db.get(UserMembership, 1).end_at == datetime(2026,11,6)
    assert eligibility(pause_api).json() == saved


def test_multiple_pauses_and_full_allowance(pause_api):
    assert confirm(pause_api, selection(days=4)).status_code == 200
    assert eligibility(pause_api).json()['pause_days_remaining'] == 6
    assert preview(pause_api, selection('2026-10-20',7)).json()['detail']['code'] == 'PAUSE_LIMIT_EXCEEDED'
    assert confirm(pause_api, selection('2026-10-20',6), key='second-pause-request').status_code == 200
    saved=eligibility(pause_api).json()
    assert not saved['can_pause'] and saved['pause_days_remaining']==0 and len(saved['history'])==2
    assert saved['current_end_at'].startswith('2026-11-11')


@pytest.mark.parametrize('body,code', [(selection('2026-09-30'),'INVALID_PAUSE_DATE'),(selection('2026-10-01'),'INVALID_PAUSE_DATE'),(selection('2026-10-30',5),'INVALID_PAUSE_DATE'),(selection(days=11),'PAUSE_LIMIT_EXCEEDED'),(selection('9999-12-31',10),'INVALID_PAUSE_DATE')])
def test_invalid_dates_and_allowance(pause_api, body, code):
    response=preview(pause_api,body)
    assert response.status_code==409 and response.json()['detail']['code']==code


def test_overlap_and_stale_preview_do_not_extend_again(pause_api):
    stale=preview(pause_api,selection('2026-10-20',2)).json()
    assert confirm(pause_api).status_code==200
    assert preview(pause_api,selection('2026-10-12',2)).json()['detail']['code']=='PAUSE_OVERLAP'
    assert confirm(pause_api,selection('2026-10-20',2),key='stale-preview-key',token=stale['preview_token']).json()['detail']['code']=='PAUSE_PREVIEW_CHANGED'
    assert len(eligibility(pause_api).json()['history'])==1


def test_owner_and_admin_policy_authorization_and_live_changes(pause_api):
    client, headers, engine = pause_api
    single='/api/v1/gym-owner/membership-plans/1'
    for who in [0,1,3]:
        assert client.put(single,headers=headers[who],json={'pause_policy':{'allowed':False,'max_pause_days':0}}).status_code==403
    changed=client.put(single,headers=headers[2],json={'pause_policy':{'allowed':False,'max_pause_days':0}})
    assert changed.status_code==200 and changed.json()['pause_policy']['allowed'] is False
    assert eligibility(pause_api,2,3).json()['can_pause'] is False
    assert preview(pause_api,mid=2,user=3).json()['detail']['code']=='PAUSE_NOT_ALLOWED'
    changed=client.put(single,headers=headers[2],json={'pause_policy':{'allowed':True,'max_pause_days':4}})
    assert changed.status_code==200
    assert eligibility(pause_api,2,3).json()['pause_days_remaining']==4
    # An owner's authenticated API cannot edit a plan owned by a different gym owner.
    with Session(engine) as db:
        gym=Gym(owner_user_id=1,name='Other owner',status='APPROVED',is_active=True)
        db.add(gym);db.flush()
        plan=GymMembershipPlan(gym_id=gym.id,name='Private plan',duration_days=30,price=100)
        db.add(plan);db.commit();other=plan.id
    assert client.put(f'/api/v1/gym-owner/membership-plans/{other}',headers=headers[2],json={'pause_policy':{'allowed':True,'max_pause_days':4}}).status_code==404
    detail=client.get('/api/v1/admin/membership-plans/1',headers=headers[0]).json()
    payload=plan_body(pause_rule={'allowed':True,'max_pause_days':7},expected_version=detail['plan']['version'])
    assert client.put('/api/v1/admin/membership-plans/1',headers=headers[2],json=payload).status_code==403
    assert client.put('/api/v1/admin/membership-plans/1',headers=headers[1],json=payload).status_code==403
    assert client.put('/api/v1/admin/membership-plans/1',headers=headers[0],json=payload).status_code==200
    assert eligibility(pause_api).json()['pause_days_remaining']==7


@pytest.mark.parametrize('policy',[{'allowed':True,'max_pause_days':0},{'allowed':True,'max_pause_days':-1},{'allowed':False,'max_pause_days':4},{'allowed':True,'max_pause_days':1.5}])
def test_invalid_policy_rejected_for_both_configurators(pause_api,policy):
    client,headers,_=pause_api
    assert client.put('/api/v1/gym-owner/membership-plans/1',headers=headers[2],json={'pause_policy':policy}).status_code==422
    assert client.post('/api/v1/admin/membership-plans',headers=headers[0],json={**plan_body(), 'code':'invalid-policy', 'pause_rule':policy}).status_code==422


def test_customer_cannot_pause_others_or_inactive_memberships(pause_api):
    assert eligibility(pause_api,1,3).status_code==404
    assert eligibility(pause_api,1,2).status_code==403
    for state in ['EXPIRED','CANCELLED']:
        with Session(pause_api[2]) as db:
            db.get(UserMembership,1).status=state;db.commit()
        assert not eligibility(pause_api).json()['can_pause']
        assert preview(pause_api).status_code==409


@pytest.mark.parametrize('mid,user,uid',[(1,1,2),(2,3,4)])
def test_pause_blocks_qr_every_gym_and_auto_resumes(pause_api,monkeypatch,mid,user,uid):
    assert confirm(pause_api,mid=mid,user=user).status_code==200
    paused=datetime(2026,10,12,12,tzinfo=timezone.utc)
    monkeypatch.setattr(pause_module,'utcnow',lambda:paused)
    monkeypatch.setattr(access_service,'utcnow',lambda:paused)
    monkeypatch.setattr(access_service,'utc_today',lambda:paused.date())
    assert eligibility(pause_api,mid,user).json()['membership_status']=='PAUSED'
    assert preview(pause_api,mid=mid,user=user).json()['detail']['code']=='MEMBERSHIP_ALREADY_PAUSED'
    response=pause_api[0].get('/api/v1/customer/access/today',headers=pause_api[1][user])
    assert response.json()=={'status':'PAUSED','code':'MEMBERSHIP_PAUSED'}
    assert pause_api[0].get('/api/v1/memberships/me',headers=pause_api[1][user]).json()[0]['status']=='PAUSED'
    with Session(pause_api[2]) as db:
        assert included_ids(db,uid,paused)==set()
        assert not active_memberships(db,uid,paused)
        assert len(active_memberships(db,uid,paused,include_paused=True))==1
        assert db.scalar(select(func.count(AccessQrToken.id)))==0
        day=next(d for d in AccessService(db).calendar_month(user_id=uid,year=2026,month=10)['days'] if str(d['date'])=='2026-10-12')
        assert day['qr_status']=='PAUSED'
    resumed=datetime(2026,10,15,12,tzinfo=timezone.utc)
    monkeypatch.setattr(pause_module,'utcnow',lambda:resumed)
    monkeypatch.setattr(access_service,'utcnow',lambda:resumed)
    monkeypatch.setattr(access_service,'utc_today',lambda:resumed.date())
    assert eligibility(pause_api,mid,user).json()['membership_status']=='ACTIVE'
    with Session(pause_api[2]) as db:
        svc=AccessService(db);token=svc.get_today_access(user_id=uid)
        assert token['status']=='ACTIVE'
        assert svc.validate_checkin(gym_id=1,qr_token=token['qr_token'])['success']


def test_existing_qr_cannot_bypass_membership_pause(pause_api):
    with Session(pause_api[2]) as db:
        svc=AccessService(db);token=svc.get_today_access(user_id=2)['qr_token']
        # Simulate a previously-issued credential while policy changes are read.
        db.add(MembershipPause(membership_id=1,request_key='server-fixture',start_date=NOW.date(),end_date=NOW.date(),days=1,previous_end_at=datetime(2026,11,1),new_end_at=datetime(2026,11,2)))
        db.commit()
        for gid in [1,2]:
            with pytest.raises(HTTPException) as error: svc.validate_checkin(gym_id=gid,qr_token=token)
            assert error.value.detail=={'code':'MEMBERSHIP_PAUSED'}
        assert db.scalar(select(func.count(Checkin.id)))==0


def test_one_paused_single_membership_does_not_disable_other_gym(pause_api,monkeypatch):
    assert confirm(pause_api,mid=2,user=3).status_code==200
    day=datetime(2026,10,12,12,tzinfo=timezone.utc)
    monkeypatch.setattr(access_service,'utcnow',lambda:day)
    monkeypatch.setattr(access_service,'utc_today',lambda:day.date())
    with Session(pause_api[2]) as db:
        plan=GymMembershipPlan(gym_id=2,name='Another single',duration_days=30,price=100)
        db.add(plan);db.flush()
        db.add(UserMembership(user_id=4,gym_id=2,plan_id=plan.id,status='ACTIVE',start_at=NOW,end_at=datetime(2026,11,1),paid_amount=100,payment_status='PAID'))
        db.commit()
        assert included_ids(db,4,day)=={2}
        qr=AccessService(db).get_today_access(user_id=4)
        assert qr['status']=='ACTIVE' and qr['gym']['id']==2
        calendar=AccessService(db).calendar_month(user_id=4,year=2026,month=10)
        assert next(d for d in calendar['days'] if str(d['date'])=='2026-10-12')['qr_status']=='ACTIVE'


def test_failed_write_rolls_back_extension_and_allowance(pause_api):
    token=preview(pause_api).json()['preview_token']
    def fail_insert(*args): raise RuntimeError('isolated failure')
    event.listen(MembershipPause,'before_insert',fail_insert)
    try:
        with pytest.raises(RuntimeError): confirm(pause_api,token=token)
    finally: event.remove(MembershipPause,'before_insert',fail_insert)
    assert eligibility(pause_api).json()['pause_days_used']==0
    assert eligibility(pause_api).json()['current_end_at'].startswith('2026-11-01')
    assert confirm(pause_api,token=token).status_code==200


def test_additive_migration_roundtrip_preserves_records():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, text, inspect
    engine=create_engine('sqlite://')
    file=Path(__file__).parents[1]/'alembic'/'versions'/'6eb14f5a7c93_membership_pause.py'
    spec=spec_from_file_location('pause_migration',file);module=module_from_spec(spec);spec.loader.exec_module(module)
    with engine.begin() as connection:
        for table in ['gym_membership_plans','platform_membership_plans']:
            connection.execute(text(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY)'))
            connection.execute(text(f'INSERT INTO {table} (id) VALUES (1)'))
        connection.execute(text('CREATE TABLE user_memberships (id INTEGER PRIMARY KEY, end_at DATETIME)'))
        connection.execute(text("INSERT INTO user_memberships VALUES (1,'2026-11-01 00:00:00')"))
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
        assert connection.execute(text('SELECT original_end_at=end_at FROM user_memberships')).scalar()==1
        assert connection.execute(text('SELECT pause_allowed,max_pause_days FROM gym_membership_plans')).first()==(0,0)
        assert 'membership_pauses' in inspect(connection).get_table_names()
        with Operations.context(MigrationContext.configure(connection)):
            module.downgrade()
        assert connection.execute(text('SELECT count(*) FROM user_memberships')).scalar()==1
        assert 'membership_pauses' not in inspect(connection).get_table_names()
    engine.dispose()


def test_policy_disable_preserves_accepted_pause_and_latest_allowance(pause_api, monkeypatch):
    assert confirm(pause_api).status_code == 200
    client, headers, engine = pause_api
    detail = client.get('/api/v1/admin/membership-plans/1', headers=headers[0]).json()
    payload = {**plan_body(), 'pause_rule': {'allowed': False, 'max_pause_days': 0}, 'expected_version': detail['plan']['version']}
    assert client.put('/api/v1/admin/membership-plans/1', headers=headers[0], json=payload).status_code == 200
    result = eligibility(pause_api).json()
    assert result['pause_days_used'] == 5 and result['pause_days_remaining'] == 0
    assert result['can_pause'] is False and len(result['history']) == 1
    paused = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(pause_module, 'utcnow', lambda: paused)
    monkeypatch.setattr(access_service, 'utcnow', lambda: paused)
    monkeypatch.setattr(access_service, 'utc_today', lambda: paused.date())
    assert eligibility(pause_api).json()['membership_status'] == 'PAUSED'
    with Session(engine) as db:
        assert AccessService(db).get_today_access(user_id=2)['status'] == 'PAUSED'
        assert db.get(UserMembership, 1).end_at == datetime(2026, 11, 6)


def test_staff_checkin_api_reports_membership_paused_not_invalid_qr(pause_api):
    from app.models.auth import Role, User, UserRole
    from app.models.staff import GymStaffAssignment
    from app.core.security import create_access_token
    client, _, engine = pause_api
    metadata = MetaData()
    for name in ('users', 'gyms', 'gym_staff_assignments'):
        table = GymStaffAssignment.metadata.tables[name].to_metadata(metadata)
        table.c.id.type = Integer()
    metadata.create_all(engine, tables=[metadata.tables['gym_staff_assignments']])
    with Session(engine) as db:
        role = Role(name='GYM_STAFF'); staff = User(email='pause-staff@example.test', password_hash='unused', status='ACTIVE')
        db.add_all([role, staff]); db.flush()
        db.add(UserRole(user_id=staff.id, role_id=role.id))
        db.add_all([GymStaffAssignment(gym_id=gid, user_id=staff.id) for gid in (1, 2)])
        db.commit(); staff_token = create_access_token(str(staff.id))
        qr = AccessService(db).get_today_access(user_id=2)['qr_token']
        db.add(MembershipPause(membership_id=1, request_key='staff-test-pause', start_date=NOW.date(), end_date=NOW.date(), days=1, previous_end_at=datetime(2026,11,1), new_end_at=datetime(2026,11,2)))
        db.commit()
    for gid in (1, 2):
        response = client.post('/api/v1/checkins/validate', headers={'Authorization': f'Bearer {staff_token}'}, json={'gym_id': gid, 'qr_token': qr})
        assert response.status_code == 200, response.text
        assert response.json()['success'] is False
        assert response.json()['status'] == 'MEMBERSHIP_PAUSED'
        assert 'paused' in response.json()['message']
    with Session(engine) as db:
        assert db.scalar(select(func.count(Checkin.id))) == 0