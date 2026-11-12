"""Real API and persistence with fake delivery; no external email/SMS calls."""
from datetime import timedelta
from unittest.mock import patch
import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session,sessionmaker
from app.core.config import settings
from app.models.auth import User
from app.models.notification import NotificationEvent
from app.models.notification_delivery import NotificationDelivery,NotificationPreference
from app.routers import notifications
from app.services import notification_workflow as workflow
from test_phase5_workflows import api as phase5_api,booking_api


@pytest.fixture
def api(phase5_api,monkeypatch):
    monkeypatch.setattr(settings,'notification_workflows_enabled',True)
    monkeypatch.setattr(settings,'notification_email_enabled',True)
    monkeypatch.setattr(workflow.account_delivery,'email_ready',lambda:True)
    sent=[]
    monkeypatch.setattr(workflow.account_delivery,'send_email',lambda *args:sent.append(args))
    phase5_api[0].app.include_router(notifications.router,prefix='/api/v1')
    with Session(phase5_api[2]) as db:
        for uid in [1,2,3,4,5]:
            user=db.get(User,uid);user.email=f'notification-{uid}@example.com';user.is_email_verified=True
        db.commit()
    return (*phase5_api,sent)


def emit(api,uid=1,kind='PASSWORD_CHANGED'):
    with Session(api[2]) as db:
        workflow.publish(db,uid,kind,1);db.commit()
        return db.scalar(select(NotificationDelivery.id).order_by(NotificationDelivery.id.desc()))


def test_preferences_are_scoped_strict_persistent_and_channel_gated(api,monkeypatch):
    client,headers,engine,_=api;path='/api/v1/notifications/preferences'
    assert client.get(path).status_code==401
    assert client.get(path,headers=headers[1]).json()['operational_email'] is False
    assert client.patch(path,headers=headers[1],json={'operational_email':True,'user_id':2}).status_code==422
    assert client.patch(path,headers=headers[1],json={'operational_email':'yes'}).status_code==422
    response=client.patch(path,headers=headers[1],json={'operational_email':True})
    assert response.status_code==200 and response.json()['operational_email']
    assert not client.get(path,headers=headers[2]).json()['operational_email']
    monkeypatch.setattr(workflow.account_delivery,'email_ready',lambda:False)
    assert client.patch(path,headers=headers[2],json={'operational_email':True}).status_code==409
    assert client.patch(path,headers=headers[1],json={'operational_email':False}).status_code==200
    with Session(engine) as db:assert not db.get(NotificationPreference,1).operational_email


def test_inbox_read_state_is_owned_paginated_and_not_delivery_state(api):
    first=emit(api);emit(api);emit(api,uid=2)
    client,headers,engine,_=api;path='/api/v1/notifications/inbox'
    data=client.get(path+'?limit=1',headers=headers[1]).json()
    assert data['total']==data['unread_count']==2 and len(data['items'])==1
    assert client.get(path+'?limit=0',headers=headers[1]).status_code==422
    assert client.get(path+'?offset=-1',headers=headers[1]).status_code==422
    assert client.post(f'{path}/{first}/read',headers=headers[2]).status_code==404
    a=client.post(f'{path}/{first}/read',headers=headers[1]);b=client.post(f'{path}/{first}/read',headers=headers[1])
    assert a.status_code==200 and a.json()==b.json()
    assert client.get(path+'?unread=true',headers=headers[1]).json()['total']==1
    with Session(engine) as db:assert db.get(NotificationDelivery,first).email_status=='QUEUED'


def test_publish_rolls_back_with_business_transaction_and_no_retroactive_mail(api):
    with Session(api[2]) as db:
        db.get(User,1).first_name='Not committed';workflow.publish(db,1,'PROFILE_UPDATED',1);db.rollback()
        assert db.scalar(select(func.count(NotificationDelivery.id)))==0
        assert db.scalar(select(func.count(NotificationEvent.id)))==0
        assert db.get(User,1).first_name!='Not committed'
    row=emit(api,kind='BOOKING_CANCELLED')
    with Session(api[2]) as db:
        assert db.get(NotificationDelivery,row).email_status=='NOT_REQUESTED'
        workflow.update_preferences(db,1,True)
    assert workflow.dispatch(sessionmaker(bind=api[2]),row)=='NOT_REQUESTED' and not api[3]


def test_worker_records_acceptance_once_not_delivery(api):
    row=emit(api);factory=sessionmaker(bind=api[2])
    assert workflow.dispatch(factory,row)=='ACCEPTED'
    assert workflow.dispatch(factory,row)=='ACCEPTED'
    assert len(api[3])==1
    with Session(api[2]) as db:
        assert db.get(NotificationDelivery,row).accepted_at
        assert db.get(NotificationDelivery,row).read_at is None
        assert db.scalar(select(NotificationEvent.status))=='RECORDED'
    assert api[0].post('/api/v1/notifications/1/mark-sent',headers=api[1][4]).status_code==409


def test_uncertain_sends_and_crashed_claims_are_never_automatically_resent(api,monkeypatch):
    row=emit(api);factory=sessionmaker(bind=api[2]);calls=[]
    def fail(*args):calls.append(1);raise TimeoutError('token=must-not-leak')
    monkeypatch.setattr(workflow.account_delivery,'send_email',fail)
    assert workflow.dispatch(factory,row)=='UNKNOWN'
    assert workflow.dispatch(factory,row)=='UNKNOWN' and len(calls)==1
    response=api[0].get('/api/v1/notifications/inbox',headers=api[1][1]);assert 'must-not-leak' not in response.text
    other=emit(api)
    with Session(api[2]) as db:
        item=db.get(NotificationDelivery,other);item.email_status='DISPATCHING';item.claimed_at=workflow.stamp()-timedelta(minutes=6);db.commit()
    assert workflow.dispatch(factory,other)=='UNKNOWN' and len(calls)==1


def test_backoff_only_before_external_send_and_bound_attempts(api,monkeypatch):
    row=emit(api);factory=sessionmaker(bind=api[2]);monkeypatch.setattr(workflow.account_delivery,'email_ready',lambda:False)
    for attempt in range(1,6):
        assert workflow.dispatch(factory,row)==('WAITING' if attempt<5 else 'FAILED')
        with Session(api[2]) as db:
            item=db.get(NotificationDelivery,row);assert item.attempts==attempt
            item.next_attempt_at=workflow.stamp()-timedelta(seconds=1);db.commit()
    assert not api[3]


@pytest.mark.parametrize('change',['optout','email','unverified','inactive'])
def test_worker_revalidates_preferences_and_recipient_before_send(api,change):
    with Session(api[2]) as db:workflow.update_preferences(db,1,True)
    row=emit(api,kind='BOOKING_CANCELLED')
    with Session(api[2]) as db:
        user=db.get(User,1)
        if change=='optout':workflow.update_preferences(db,1,False)
        elif change=='email':user.email='different@example.com'
        elif change=='unverified':user.is_email_verified=False
        else:user.status='INACTIVE'
        db.commit()
    assert workflow.dispatch(sessionmaker(bind=api[2]),row)=='SUPPRESSED' and not api[3]


def test_security_notice_not_affected_by_optional_optout_and_disabled_gate(api,monkeypatch):
    row=emit(api);assert workflow.dispatch(sessionmaker(bind=api[2]),row)=='ACCEPTED'
    monkeypatch.setattr(settings,'notification_workflows_enabled',False)
    with Session(api[2]) as db:
        before=db.scalar(select(func.count(NotificationDelivery.id)))
        workflow.publish(db,1,'PASSWORD_CHANGED',1);db.commit()
        assert db.scalar(select(func.count(NotificationDelivery.id)))==before
    assert not api[0].get('/api/v1/notifications/inbox',headers=api[1][1]).json()['enabled']
    assert api[0].patch('/api/v1/notifications/preferences',headers=api[1][1],json={'operational_email':False}).status_code==409


def test_legacy_payloads_and_errors_never_echo_secrets(api):
    with Session(api[2]) as db:
        db.add(NotificationEvent(user_id=1,event_type='LEGACY',status='FAILED',payload_json='{"password":"secret","resource_id":2}',error_message='token=secret'))
        db.add(NotificationEvent(user_id=1,event_type='LEGACY',status='FAILED',payload_json='invalid secret'));db.commit()
    response=api[0].get('/api/v1/notifications/me',headers=api[1][1]);assert response.status_code==200
    assert 'secret' not in response.text and 'password' not in response.text
    assert response.headers['Cache-Control']=='no-store'


def test_disabled_sender_and_changed_contact_do_not_send_or_backfill(api,monkeypatch):
    monkeypatch.setattr(settings,'notification_email_enabled',False)
    row=emit(api)
    assert workflow.dispatch(sessionmaker(bind=api[2]),row)=='DISABLED'
    monkeypatch.setattr(settings,'notification_email_enabled',True)
    assert workflow.dispatch(sessionmaker(bind=api[2]),row)=='NOT_REQUESTED'
    assert not api[3]


def test_post_send_commit_failure_becomes_unknown_without_replay(api):
    row=emit(api);factory=sessionmaker(bind=api[2]);original=Session.commit;count=[]
    def fail_final(db):
        count.append(1)
        if len(count)==2:raise RuntimeError('fixture database unavailable after send')
        return original(db)
    with patch.object(Session,'commit',fail_final):
        with pytest.raises(RuntimeError):workflow.dispatch(factory,row)
    assert len(api[3])==1
    with Session(api[2]) as db:
        item=db.get(NotificationDelivery,row)
        assert item.email_status=='DISPATCHING'
        item.claimed_at=workflow.stamp()-timedelta(minutes=6);db.commit()
    assert workflow.dispatch(factory,row)=='UNKNOWN' and len(api[3])==1


def test_booking_cancellation_generates_one_notification_on_retry(api):
    from test_booking_access_qr import create,NOW
    booking=create(api[:3],day=NOW.date()+timedelta(days=2))
    for _ in range(2):
        assert api[0].post(f"/api/v1/gym-owner/bookings/{booking['id']}/cancel",headers=api[1][2],json={}).status_code==200
    with Session(api[2]) as db:
        items=db.scalars(select(NotificationDelivery)).all()
        assert len(items)==1 and items[0].user_id==1 and items[0].kind=='BOOKING_CANCELLED'


def test_admin_delivery_status_excludes_sensitive_fields_and_wrong_roles(api):
    emit(api)
    for actor in [1,2,3]:
        assert api[0].get('/api/v1/notifications/delivery-status',headers=api[1][actor]).status_code==403
    response=api[0].get('/api/v1/notifications/delivery-status',headers=api[1][4])
    assert response.status_code==200 and response.json()['total']==1
    assert 'recipient_hash' not in response.text and '@' not in response.text and 'claim_id' not in response.text


def test_support_configuration_is_validated_and_not_a_fake_ticket_service(api,monkeypatch):
    monkeypatch.setattr(settings,'support_email','support@example.com')
    response=api[0].get('/api/v1/meta/support');assert response.json()['email']=='support@example.com'
    assert response.json()['ticketing_available'] == (settings.support_workflows_enabled and settings.operational_workflows_enabled)
    monkeypatch.setattr(settings,'support_email','bad\nsecret')
    response=api[0].get('/api/v1/meta/support');assert response.json()['email'] is None and 'secret' not in response.text