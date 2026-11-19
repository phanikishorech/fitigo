"""Evidence/outbox atomicity and real production admission on disposable MySQL."""
from datetime import timedelta
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func, event
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.time import stored_instant
from app.models.payment_checkout import PaymentCheckout
from app.models.membership import UserMembership
from app.models.booking import Booking, Payment
from app.models.access import AccessQrToken, Checkin
from app.models.gym import Gym
from app.models.wallet import WalletAccount
from app.models.source_evidence import SourceEvidence, SourceOutbox, GymOwnerEvidence
from app.services import source_evidence as evidence, source_outbox as worker, access_service, booking_access_service
from app.services import booking_cancellation, membership_transfer
from test_customer_policy_mysql import database


@pytest.fixture(autouse=True)
def on(monkeypatch):monkeypatch.setattr(settings,'source_evidence_enabled',True)


def link(db,now,kind='MULTI_GYM',mode='test'):
    checkout=PaymentCheckout(id=str(uuid4()),user_id=1,source_key=str(uuid4()),kind=kind,provider='RAZORPAY',
        mode=mode,key_id='fixture',amount=100,currency='INR',snapshot={},status='PAID',created_at=stored_instant(now))
    db.add(checkout);db.flush()
    if kind=='MULTI_GYM':db.get(UserMembership,1).gateway_checkout_id=checkout.id
    else:db.get(Booking,1).checkout_id=checkout.id
    db.commit();return checkout.id


def test_production_membership_issue_admit_owner_snapshot_and_analytics(database):
    engine,now=database
    with Session(engine) as db:
        link(db,now)
        token=access_service.AccessService(db).get_today_access(user_id=1)['qr_token']
        qr=db.scalars(select(AccessQrToken)).one()
        assert qr.valid_from==stored_instant(now) and qr.expires_at==stored_instant(now+timedelta(minutes=5))
        result=access_service.AccessService(db).validate_checkin(gym_id=1,qr_token=token,scanned_by=3)
        assert result['success']
        row=db.scalars(select(SourceEvidence).where(SourceEvidence.event_type=='MULTI_GYM_VISIT_VERIFIED')).one()
        assert row.payload['membership_id']==1 and row.payload['daily_access_id']
        assert row.payload['access_consumption_status']=='USED' and row.payload['owner_id_at_event']==3
        assert row.mode=='test' and row.payload['valid_from']
        scan=db.scalars(select(Checkin)).one()
        assert scan.checkin_time>=qr.valid_from and scan.checkin_time<qr.expires_at
        from app.services.admin_financial_queries import visits
        visit_query=visits('test')
        assert db.scalar(select(func.count()).select_from(visit_query))==1
        db.get(Gym,1).owner_user_id=2;db.commit();db.expire_all()
        assert db.get(SourceEvidence,row.id).payload['owner_id_at_event']==3
        assert db.scalar(select(GymOwnerEvidence.owner_user_id))==3
        assert db.scalar(select(SourceOutbox.agreement_pin_id)) is None


def test_membership_qr_expiry_and_not_before(database,monkeypatch):
    engine,now=database
    with Session(engine) as db:
        link(db,now);token=access_service.AccessService(db).get_today_access(user_id=1)['qr_token']
        monkeypatch.setattr(access_service,'utcnow',lambda:now+timedelta(minutes=5))
        with pytest.raises(HTTPException):access_service.AccessService(db).validate_checkin(gym_id=1,qr_token=token,scanned_by=3)
        assert db.scalar(select(func.count(Checkin.id)))==0
        assert db.scalar(select(func.count(SourceEvidence.id)))==0


def test_partial_booking_admission_does_not_admit_all(database,monkeypatch):
    engine,now=database
    monkeypatch.setattr(booking_access_service,'utcnow',lambda:now+timedelta(hours=3))
    with Session(engine) as db:
        link(db,now,'BOOKING')
        b=db.get(Booking,1);b.quantity=2;b.visitor_names=['One','Two'];b.total_price=200
        db.get(Payment,1).amount=200;db.commit()
        passes=booking_access_service.BookingAccessService(db).issue(1,1)['passes']
        access_service.AccessService(db).validate_checkin(gym_id=1,qr_token=passes[0]['qr_token'],scanned_by=3)
        rows=list(db.scalars(select(SourceEvidence).where(SourceEvidence.event_type=='BOOKING_VISITOR_ATTENDED')))
        assert len(rows)==1 and rows[0].payload['visitor_index']==0
        assert db.get(Booking,1).attendance_status is None
        assert db.scalar(select(func.count(SourceEvidence.id)).where(SourceEvidence.event_type=='BOOKING_NO_SHOW_CONFIRMED'))==0


def test_outbox_failure_rolls_back_cancellation_credit(database,monkeypatch):
    engine,now=database
    def failure(*args,**kwargs):raise RuntimeError('Simulated disk failure')
    monkeypatch.setattr(evidence,'snapshot',failure)
    with Session(engine) as db:
        with pytest.raises(RuntimeError):booking_cancellation.cancel(db,booking_id=1,actor_id=1,customer_id=1)
        assert db.get(Booking,1).status=='CONFIRMED' and db.get(WalletAccount,1).balance==500
        assert db.scalar(select(func.count(SourceEvidence.id)))==0


def test_cancellation_and_credit_evidence_atomic(database):
    engine,now=database
    with Session(engine) as db:
        booking_cancellation.cancel(db,booking_id=1,actor_id=1,customer_id=1)
        assert set(db.scalars(select(SourceEvidence.event_type)))=={'BOOKING_CANCELLED','WALLET_CREDIT_CONFIRMED'}
        assert db.scalar(select(func.count(SourceOutbox.id)))==2


def test_transfer_preserves_purchaser_holder_and_reference(database):
    engine,now=database
    with Session(engine) as db:
        link(db,now)
        preview=membership_transfer.preview(db,1,1,'policy-2@example.com')
        result=membership_transfer.confirm(db,1,1,preview['confirmation_token'],'source-transfer')
        row=db.scalars(select(SourceEvidence)).one()
        assert row.payload['original_purchaser_id']==1 and row.payload['holder_id_at_event']==2
        assert row.payload['transfer_id']==result['reference']
        assert row.payload['financial_beneficiary_id'] is None


def test_crash_recovery_fencing_and_idempotent_processing(database):
    engine,now=database
    with Session(engine) as db:
        cid=link(db,now)
        row=evidence.snapshot(db,'MEMBERSHIP_ACTIVATED','MEMBERSHIP',1,checkout=db.get(PaymentCheckout,cid),occurred_at=now)
        db.commit()
        assert worker.claim(db,'live',now=now+timedelta(days=100)) is None
        first=worker.claim(db,'test',now=now+timedelta(days=100),lease_seconds=2);db.commit()
    with Session(engine) as db:
        second=worker.claim(db,'test',now=now+timedelta(days=100,seconds=3));db.commit()
        assert first[0]==second[0] and first[1]!=second[1]
        with pytest.raises(ValueError):worker.finish(db,*first,'test',now=now+timedelta(days=100,seconds=4))
        db.rollback()
        result=worker.finish(db,*second,'test',now=now+timedelta(days=100,seconds=4));db.commit()
        assert result.status=='AWAITING_POLICY' and result.retry_count==2
        assert worker.finish(db,*second,'test',now=now+timedelta(days=100,seconds=5)).id==result.id
        assert result.agreement_pin_id is None


def test_unknown_environment_quarantined_and_cross_mode_rejected(database):
    engine,now=database
    with Session(engine) as db:
        cid=link(db,now)
        with pytest.raises(HTTPException):evidence.snapshot(db,'PAYMENT_CAPTURED','CHECKOUT',cid,checkout=db.get(PaymentCheckout,cid),mode='live')
        db.rollback()
        row=evidence.snapshot(db,'MEMBERSHIP_PAUSED','LEGACY',1,occurred_at=now)
        db.commit()
        assert row.evidence_status=='ENVIRONMENT_UNAVAILABLE'
        assert db.scalar(select(func.count(SourceOutbox.id)))==0


def test_authorized_no_show_after_window_and_not_before(database,monkeypatch):
    from app.services.booking_service import BookingService
    from app.services import owner_booking_policy
    engine,now=database
    with Session(engine) as db:
        monkeypatch.setattr(owner_booking_policy,'utcnow',lambda:now)
        with pytest.raises(HTTPException):BookingService(db).owner_mark_attendance(owner_user_id=3,booking_id=1,attendance_status='NO_SHOW')
        db.rollback()
        closed=now+timedelta(hours=8,minutes=1)
        monkeypatch.setattr(owner_booking_policy,'utcnow',lambda:closed)
        monkeypatch.setattr(BookingService,'_now',lambda self:stored_instant(closed))
        BookingService(db).owner_mark_attendance(owner_user_id=3,booking_id=1,attendance_status='NO_SHOW')
        row=db.scalars(select(SourceEvidence)).one()
        assert row.event_type=='BOOKING_NO_SHOW_CONFIRMED' and row.payload['visitor_indices']==[0]
        assert row.payload['actor_id']==3 and row.mode=='test'
        assert db.scalar(select(func.count(Checkin.id)))==0


def test_pause_evidence_from_production_service(database):
    from app.models.platform_membership import PlatformMembershipPlan
    from app.services.membership_pause_service import MembershipPauseService
    from app.schemas.membership_pause import PauseRequest, PauseConfirm
    engine,now=database
    with Session(engine) as db:
        link(db,now)
        plan=PlatformMembershipPlan(code='source-pause',name='Evidence',duration_value=30,duration_unit='DAY',base_price=100,currency='INR',is_active=True,pause_allowed=True,max_pause_days=5)
        db.add(plan);db.flush();member=db.get(UserMembership,1);member.platform_plan_id=plan.id;db.commit()
        service=MembershipPauseService(db)
        request=PauseRequest(start_date=now.date()+timedelta(days=1),days=2)
        preview=service.preview(member,request)
        request=PauseConfirm(start_date=request.start_date,days=2,accepted_preview=preview.preview_token)
        service.create(1,1,request,'source-pause-request')
        row=db.scalars(select(SourceEvidence)).one()
        assert row.event_type=='MEMBERSHIP_PAUSED' and row.payload['days']==2
        assert row.payload['new_end_at']!=row.payload['previous_end_at']
        service.create(1,1,request,'source-pause-request')
        assert db.scalar(select(func.count(SourceEvidence.id)))==1


def test_worker_retry_and_claim_rollback(database):
    engine,now=database
    with Session(engine) as db:
        cid=link(db,now)
        evidence.snapshot(db,'PAYMENT_CAPTURED','CHECKOUT',cid,checkout=db.get(PaymentCheckout,cid),occurred_at=now);db.commit()
        at=now+timedelta(days=100)
        lost=worker.claim(db,'test',now=at);db.rollback()
        lease=worker.claim(db,'test',now=at);db.commit()
        assert lost[0]==lease[0]
        row=worker.finish(db,*lease,'test',now=at,error_code='contains-a-secret');db.commit()
        assert row.last_error=='SOURCE_HANDOFF_RETRY' and row.status=='RETRY'
        assert worker.claim(db,'test',now=at) is None
        lease=worker.claim(db,'test',now=at+timedelta(seconds=3));db.commit()
        worker.finish(db,*lease,'test',now=at+timedelta(seconds=3));db.rollback()
        # Crash before acknowledgement commit leaves the durable claim recoverable.
        lease=worker.claim(db,'test',now=at+timedelta(seconds=70));db.commit()
        assert lease is not None
        assert worker.finish(db,*lease,'test',now=at+timedelta(seconds=70)).status=='AWAITING_POLICY'
        db.commit()


def test_source_migration_preserves_records_and_refuses_evidence_loss(database,monkeypatch):
    from pathlib import Path
    from importlib.util import spec_from_file_location,module_from_spec
    from alembic.operations import Operations
    from alembic.migration import MigrationContext
    path=Path(__file__).resolve().parents[1]/'alembic/versions/f68a92dc1480_source_evidence.py'
    spec=spec_from_file_location('source_migration',path);module=module_from_spec(spec);spec.loader.exec_module(module)
    engine,now=database
    with engine.begin() as c:
        monkeypatch.setattr(module,'op',Operations(MigrationContext.configure(c)))
        from allocation_migration_helper import allocation_migration
        child=allocation_migration(c)
        child.downgrade();module.downgrade();module.upgrade();child.upgrade()
    with Session(engine) as db:
        assert db.get(Booking,1).status=='CONFIRMED'
        evidence.snapshot(db,'LEGACY_OBSERVATION','MEMBERSHIP',1,occurred_at=now);db.commit()
        row=db.scalars(select(SourceEvidence)).one();row.mode='test'
        with pytest.raises(ValueError,match='immutable'):db.commit()
        db.rollback()
    with engine.begin() as c:
        monkeypatch.setattr(module,'op',Operations(MigrationContext.configure(c)))
        with pytest.raises(RuntimeError,match='evidence'):module.downgrade()


def test_competing_workers_claim_one_event(database):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    engine,now=database
    with Session(engine) as db:
        cid=link(db,now)
        evidence.snapshot(db,'MEMBERSHIP_ACTIVATED','MEMBERSHIP',1,checkout=db.get(PaymentCheckout,cid),occurred_at=now);db.commit()
    barrier=Barrier(2)
    def take(_):
        with Session(engine) as db:
            barrier.wait(timeout=20)
            lease=worker.claim(db,'test',now=now+timedelta(days=100));db.commit();return lease
    with ThreadPoolExecutor(max_workers=2) as pool:leases=list(pool.map(take,range(2)))
    assert sum(lease is not None for lease in leases)==1


def test_missing_schema_fails_closed_before_business_commit(database,monkeypatch):
    from app.models.source_evidence import GymOwnerEvidence
    engine,now=database
    with engine.begin() as connection:
        from allocation_migration_helper import allocation_migration
        allocation_migration(connection).downgrade()
        GymOwnerEvidence.__table__.drop(connection)
    with Session(engine) as db:
        with pytest.raises(HTTPException) as failure:booking_cancellation.cancel(db,booking_id=1,actor_id=1,customer_id=1)
        assert failure.value.status_code==503
        assert db.get(Booking,1).status=='CONFIRMED' and db.get(WalletAccount,1).balance==500