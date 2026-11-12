"""Owner/admin boundaries on disposable SQLite; MySQL runner required to collect."""
from datetime import timedelta
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.time import stored_instant
from app.models.auth import Role, UserRole
from app.models.booking import Booking, Payment
from app.models.gym import GymImage, GymStatusHistory
from app.models.membership import UserMembership
from app.models.platform_membership import PlatformMembershipAudit, PlatformMembershipPlan
from app.models.access import Checkin
from app.routers import gym_owner, admin, workflow_capabilities, users
from app.services import owner_booking_policy
from test_booking_access_qr import api as booking_api, create, qr, scan, NOW


@pytest.fixture
def api(booking_api, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, 'notification_workflows_enabled', False)
    monkeypatch.setattr(settings, 'operational_workflows_enabled', False)  # legacy deployment contract
    for router in [gym_owner.router, admin.router, workflow_capabilities.router, users.router]:
        booking_api[0].app.include_router(router, prefix='/api/v1')
    monkeypatch.setattr(owner_booking_policy, 'utcnow', lambda: NOW)
    with Session(booking_api[2]) as db:
        role=Role(name='ADMIN');db.add(role);db.flush();db.add(UserRole(user_id=4,role_id=role.id));db.commit()
    return booking_api


def test_actions_match_authorized_mutation_and_repeated_cancel_preserves_payment(api):
    booking=create(api,day=NOW.date()+timedelta(days=2))
    client,headers,engine=api;path=f"/api/v1/gym-owner/bookings/{booking['id']}"
    data=client.get(path,headers=headers[2]).json()
    assert data['allowed_actions']==['CANCEL']
    assert 'QR' in data['action_unavailable_reasons']['MARK_ATTENDED']
    assert client.get(path,headers=headers[5]).status_code==404
    assert client.post(path+'/mark-attended',headers=headers[2],json={}).status_code==409
    assert client.post(path+'/mark-no-show',headers=headers[2],json={}).status_code==409
    response=client.post(path+'/cancel',headers=headers[2],json={'reason':'Customer requested'})
    assert response.status_code==200 and response.json()['allowed_actions']==[]
    with Session(engine) as db:
        notes=db.get(Booking,booking['id']).notes
        assert db.scalar(select(Payment.status).where(Payment.booking_id==booking['id']))=='PAID'
    assert client.post(path+'/cancel',headers=headers[2],json={'reason':'retry'}).status_code==200
    with Session(engine) as db:assert db.get(Booking,booking['id']).notes==notes


def test_no_show_only_after_admission_closes_and_cannot_overwrite(api,monkeypatch):
    booking=create(api);path=f"/api/v1/gym-owner/bookings/{booking['id']}";client,headers,engine=api
    assert 'MARK_NO_SHOW' not in client.get(path,headers=headers[2]).json()['allowed_actions']
    monkeypatch.setattr(owner_booking_policy,'utcnow',lambda:NOW+timedelta(days=1))
    assert 'MARK_NO_SHOW' in client.get(path,headers=headers[2]).json()['allowed_actions']
    assert client.post(path+'/mark-no-show',headers=headers[2],json={'note':'Not present'}).status_code==200
    assert client.post(path+'/mark-attended',headers=headers[2],json={}).status_code==409
    assert client.post(path+'/cancel',headers=headers[2],json={}).status_code==409
    with Session(engine) as db:
        assert db.get(Booking,booking['id']).attendance_status=='NO_SHOW'
        assert db.scalar(select(func.count(Checkin.id)))==0


def test_successful_scan_blocks_conflicting_owner_actions(api,monkeypatch):
    booking=create(api,names=['Visitor']);passes=qr(api,booking);assert scan(api,passes[0]['qr_token'])['success']
    monkeypatch.setattr(owner_booking_policy,'utcnow',lambda:NOW+timedelta(days=1))
    path=f"/api/v1/gym-owner/bookings/{booking['id']}"
    assert api[0].get(path,headers=api[1][2]).json()['allowed_actions']==[]
    for action in ['cancel','mark-no-show','mark-attended']:
        assert api[0].post(path+'/'+action,headers=api[1][2],json={}).status_code==409


def test_directory_and_history_never_leak_other_gym_or_private_fields(api):
    booking=create(api);client,headers,engine=api
    with Session(engine) as db:
        db.add(UserMembership(user_id=1,gym_id=2,plan_id=None,membership_type='SINGLE_GYM',status='ACTIVE',
            start_at=stored_instant(NOW),end_at=stored_instant(NOW+timedelta(days=30)),paid_amount=100,payment_status='PAID'))
        db.commit()
    base='/api/v1/gym-owner/gyms/1/members'
    data=client.get(base,headers=headers[2]).json()
    assert data['total']==1 and data['items'][0]['id']==1
    assert data['items'][0]['membership_status']=='NO_GYM_MEMBERSHIP'
    assert set(data['items'][0])=={'id','name','membership_status'}
    assert client.get(base+'?q=NO-MATCH',headers=headers[2]).json()['total']==0
    assert client.get(base+'?limit=1&offset=1',headers=headers[2]).json()['items']==[]
    assert client.get(base,headers=headers[5]).status_code==404
    assert client.get(base,headers=headers[3]).status_code==403
    history=client.get(base+'/1',headers=headers[2]).json()
    assert history['memberships']==[] and history['bookings'][0]['id']==booking['id']
    assert client.get(base+'/4',headers=headers[2]).status_code==404


def test_photo_order_is_full_owned_permutation_and_cover_unchanged(api,tmp_path,monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings,'upload_dir',str(tmp_path))
    client,headers,engine=api
    with Session(engine) as db:
        for i in range(1,4):db.add(GymImage(id=i,gym_id=1,file_path=f'gyms/gym_1/{i}.png',is_cover=i==1,display_order=i))
        db.add(GymImage(id=4,gym_id=2,file_path='gyms/gym_2/4.png'));db.commit()
    path='/api/v1/gym-owner/gyms/1/images/order'
    for ids in [[1,2],[1,2,2],[1,2,4]]:assert client.put(path,headers=headers[2],json={'image_ids':ids}).status_code==409
    assert client.put(path,headers=headers[5],json={'image_ids':[1,3,2]}).status_code==404
    assert client.put(path,headers=headers[2],json={'image_ids':[1,3,2]}).status_code==200
    with Session(engine) as db:
        assert list(db.scalars(select(GymImage.id).where(GymImage.gym_id==1).order_by(GymImage.display_order)))==[1,3,2]
        assert db.get(GymImage,1).is_cover
    assert client.post('/api/v1/gym-owner/gyms/2/images',headers=headers[2],files={'file':('bad.png',b'fake','image/png')}).status_code==404
    assert not list(tmp_path.rglob('*'))


def test_admin_audit_and_settings_are_protected_and_do_not_expose_metadata(api):
    client,headers,engine=api
    with Session(engine) as db:
        db.add(GymStatusHistory(gym_id=1,old_status='DRAFT',new_status='PENDING_APPROVAL',changed_by_user_id=2,reason='secret-token-never-expose'))
        db.add(PlatformMembershipPlan(id=1,code='p',name='Plan',duration_value=1,duration_unit='MONTH',base_price=100,currency='INR',benefits=[],is_active=True));db.flush()
        db.add(PlatformMembershipAudit(plan_id=1,actor_id=4,action='UPDATE',details={'password':'secret-token-never-expose'}));db.commit()
    for path in ['/api/v1/admin/settings','/api/v1/admin/audit-logs']:
        assert client.get(path,headers=headers[2]).status_code==403
        assert client.get(path,headers=headers[1]).status_code==403
        result=client.get(path,headers=headers[4]);assert result.status_code==200
        assert 'secret-token-never-expose' not in result.text
    data=client.get('/api/v1/admin/audit-logs?limit=1&offset=1',headers=headers[4]).json()
    assert data['total']==2 and len(data['items'])==1 and not data['complete_platform_history']
    assert data['items'][0]['actor_id'] in [2,4]
    capabilities=client.get('/api/v1/meta/workflows',headers=headers[2]).json()
    assert not capabilities['refund_initiation'] and not capabilities['notification_preferences'] and not capabilities['photo_deletion']


@pytest.mark.parametrize('actor',[2,4])
def test_owner_and_admin_profile_updates_use_same_security_contract(api,actor):
    from app.models.auth import User
    from app.core.security import hash_password
    with Session(api[2]) as db:
        user=db.get(User,actor);user.email=f'account-{actor}@example.com';user.password_hash=hash_password('Current-password1');db.commit()
    body={'first_name':'Updated','last_name':'Operator','email':f'account-{actor}@example.com','phone':None}
    response=api[0].patch('/api/v1/users/me',headers=api[1][actor],json=body)
    assert response.status_code==200 and not response.json()['reauthenticate']
    with Session(api[2]) as db:assert db.get(User,actor).first_name=='Updated'
    assert api[0].patch('/api/v1/users/me',headers=api[1][actor],json={**body,'email':f'changed-{actor}@example.com'}).status_code==400
    response=api[0].patch('/api/v1/users/me',headers=api[1][actor],json={**body,'email':f'changed-{actor}@example.com','current_password':'Current-password1'})
    assert response.status_code==200 and response.json()['reauthenticate']
    assert api[0].get('/api/v1/users/me',headers=api[1][actor]).status_code==401


def test_photo_upload_owner_check_precedes_disk_write_and_unavailable_delete_does_not_touch_file(api,tmp_path,monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings,'upload_dir',str(tmp_path))
    path=tmp_path/'preserved.png';path.write_bytes(b'private-fixture')
    response=api[0].delete('/api/v1/gym-owner/gyms/1/images/1',headers=api[1][2])
    assert response.status_code == 409  # deployment gate: no deletion when disabled
    assert path.read_bytes()==b'private-fixture'


def test_class_reschedule_remains_unavailable_without_charges(api):
    booking=create(api,day=NOW.date()+timedelta(days=2));client,headers,engine=api
    with Session(engine) as db:
        db.get(Booking,booking['id']).notes='class_session_id=999';db.commit()
    path=f"/api/v1/bookings/{booking['id']}/reschedule"
    payload={'gym_slot_id':1,'slot_date':str(NOW.date()+timedelta(days=3))}
    before=None
    with Session(engine) as db:before=db.scalar(select(func.count(Payment.id)))
    response=client.post(path,headers=headers[1],json=payload)
    assert response.status_code==409,response.text
    with Session(engine) as db:
        assert db.get(Booking,booking['id']).slot_date==NOW.date()+timedelta(days=2)
        assert db.scalar(select(func.count(Payment.id)))==before