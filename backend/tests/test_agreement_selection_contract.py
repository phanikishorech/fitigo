"""Phase 2 selection metadata only; disposable MySQL, no journal/calculation."""
from datetime import timedelta
from uuid import uuid4
import hashlib
import json
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from app.models.payment_checkout import PaymentCheckout
from app.models.booking import Booking
from app.models.financial_agreement import FinancialAgreementPin, FinancialAgreementVersion
from app.schemas.financial_agreement import AgreementCreate
from app.schemas.accounting_policy import AccountingPolicy
from app.services import financial_agreements
from app.services.agreement_selection import select_for_source, pin_for_source
from test_financial_agreements import configured_api, mysql_api, payload, post, NOW, migration_module


def setup_source(api, rule='CHECKOUT_CREATED', approved=True, mode='test'):
    body=payload()
    contract=AccountingPolicy().model_dump(mode='json')
    contract['selection']['BOOKING_PURCHASE']={'instant':rule,'approval':{'status':'APPROVED','reference':'Selection decision'} if approved else {'status':'AWAITING_APPROVAL','reference':None}}
    body['terms']['policy_contract']=contract
    response=post(api,body);assert response.status_code==200,response.text
    with Session(api[2]) as db:
        checkout=PaymentCheckout(id=str(uuid4()),user_id=3,source_key=str(uuid4()),kind='BOOKING',mode=mode,provider='RAZORPAY',key_id='test',amount=150,currency='INR',snapshot={},status='PAID',created_at=(NOW+timedelta(days=2)).replace(tzinfo=None))
        db.add(checkout);db.flush()
        booking=Booking(user_id=3,gym_id=1,gym_slot_id=1,slot_date=(NOW+timedelta(days=3)).date(),quantity=1,unit_price=150,total_price=150,currency='INR',status='CONFIRMED',expires_at=(NOW+timedelta(days=3)).replace(tzinfo=None),checkout_id=checkout.id)
        db.add(booking);db.commit()
        return dict(checkout_id=checkout.id,booking_id=booking.id,context='BOOKING_PURCHASE',selection_policy_version_id=response.json()['id'])


def test_explicit_source_selection_and_immutable_pin(configured_api):
    args=setup_source(configured_api)
    with Session(configured_api[2]) as db:
        selection=select_for_source(db,**args)
        assert selection['mode']=='test' and selection['posting_eligible'] is False
        assert selection['evidence']['gym_owner_id_at_event'] is None
        assert selection['evidence']['original_purchaser_id']==3
        assert db.scalar(select(func.count(FinancialAgreementPin.id)))==0
        pin=pin_for_source(db,**args);db.commit();identifier=pin.id
        assert pin_for_source(db,**args).id==identifier
        db.rollback()
        pin=db.get(FinancialAgreementPin,identifier);pin.mode='live'
        with pytest.raises(ValueError,match='immutable'):db.commit()
        db.rollback()
        assert db.scalar(select(func.count(FinancialAgreementPin.id)))==1


@pytest.mark.parametrize('rule,approved,mode,code', [('CHECKOUT_CREATED',False,'test','POLICY_MISSING'),
    ('PAYMENT_CAPTURED',True,'test','SOURCE_DATA_MISSING'),('CHECKOUT_CREATED',True,'live','RECONCILIATION_REQUIRED')])
def test_missing_approval_capture_and_environment_fail_closed(configured_api,rule,approved,mode,code):
    args=setup_source(configured_api,rule,approved,mode)
    with Session(configured_api[2]) as db:
        with pytest.raises(HTTPException) as error:pin_for_source(db,**args)
        assert error.value.detail['code']==code
        db.rollback();assert db.scalar(select(func.count(FinancialAgreementPin.id)))==0


def test_future_agreement_cannot_be_applied_to_earlier_source(configured_api):
    args=setup_source(configured_api)
    with Session(configured_api[2]) as db:
        db.get(PaymentCheckout,args['checkout_id']).created_at=NOW.replace(tzinfo=None);db.commit()
        with pytest.raises(HTTPException) as error:select_for_source(db,**args)
        assert error.value.detail['code']=='POLICY_MISSING'


def test_old_request_hash_survives_optional_policy_field(configured_api):
    body=payload();parsed=AgreementCreate(**body)
    canonical=parsed.model_dump(mode='json');canonical['terms'].pop('policy_contract')
    canonical['terms'].pop('marketplace_contract')
    canonical['terms'].pop('visit_payout_contract')
    legacy_hash=hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    response=post(configured_api,body,'legacy-retry-key');assert response.status_code==200,response.text
    with Session(configured_api[2]) as db:
        row=db.get(FinancialAgreementVersion,response.json()['id'])
        assert row.request_hash==legacy_hash and 'policy_contract' not in row.terms
    assert post(configured_api,body,'legacy-retry-key').json()['id']==response.json()['id']


def test_validation_endpoint_does_not_save(configured_api):
    client,headers,engine=configured_api
    terms=payload()['terms'];terms['policy_contract']=AccountingPolicy().model_dump(mode='json')
    endpoint='/api/v1/admin/financial-agreements/policy-validation'
    assert client.post(endpoint,json=terms).status_code==401
    assert client.post(endpoint,json=terms,headers=headers[1]).status_code==403
    response=client.post(endpoint,json=terms,headers=headers[5]);assert response.status_code==200,response.text
    assert response.json()['posting_eligible'] is False
    assert response.json()['status']=='NOT_CONFIGURED'
    with Session(engine) as db:
        assert db.scalar(select(func.count(FinancialAgreementVersion.id)))==0
        assert db.scalar(select(func.count(FinancialAgreementPin.id)))==0


def test_pin_migration_no_backfill_and_refuses_evidence_loss(configured_api,monkeypatch):
    from importlib.util import spec_from_file_location,module_from_spec
    from pathlib import Path
    from alembic.operations import Operations
    from alembic.migration import MigrationContext
    path=Path(__file__).resolve().parents[1]/'alembic/versions/e57f81cb0379_policy_evidence_pins.py'
    spec=spec_from_file_location('pin_migration',path);migration=module_from_spec(spec);spec.loader.exec_module(migration)
    child_path=path.parent/'f68a92dc1480_source_evidence.py'
    child_spec=spec_from_file_location('source_migration_child',child_path);child=module_from_spec(child_spec);child_spec.loader.exec_module(child)
    args=setup_source(configured_api)
    with configured_api[2].begin() as c:
        monkeypatch.setattr(migration,'op',Operations(MigrationContext.configure(c)))
        prior=c.scalar(text('SELECT COUNT(*) FROM financial_agreement_versions'))
        monkeypatch.setattr(child,'op',Operations(MigrationContext.configure(c)))
        from allocation_migration_helper import allocation_migration
        allocation=allocation_migration(c)
        allocation.downgrade();child.downgrade();migration.downgrade();migration.upgrade();child.upgrade();allocation.upgrade()
        assert c.scalar(text('SELECT COUNT(*) FROM financial_agreement_versions'))==prior
        assert c.scalar(text('SELECT COUNT(*) FROM financial_agreement_pins'))==0
    with Session(configured_api[2]) as db:pin_for_source(db,**args);db.commit()
    with configured_api[2].begin() as c:
        monkeypatch.setattr(migration,'op',Operations(MigrationContext.configure(c)))
        with pytest.raises(RuntimeError,match='evidence'):migration.downgrade()


def test_pins_survive_new_agreement_versions_and_concurrent_retries(configured_api):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    args=setup_source(configured_api)
    barrier=Barrier(2)
    def pin(_):
        with Session(configured_api[2]) as db:
            db.scalar(select(func.count(FinancialAgreementVersion.id)))
            barrier.wait(timeout=15)
            row=pin_for_source(db,**args);db.commit();return row.id
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(pin,range(2)))
    assert results[0]==results[1]
    changed=payload(version=1,days=3);changed['terms']['attended']={'gym_percent':'80.00','fitigo_percent':'20.00'}
    new=post(configured_api,changed);assert new.status_code==200,new.text
    with Session(configured_api[2]) as db:
        original=db.get(FinancialAgreementPin,results[0]);before=original.evidence_hash
        assert pin_for_source(db,**args).id==original.id
        assert original.agreement_version_id==args['selection_policy_version_id']
        assert original.evidence_hash==before
        with pytest.raises(HTTPException):pin_for_source(db,**{**args,'selection_policy_version_id':new.json()['id']})
        db.rollback()


@pytest.mark.parametrize('context,instant', [('BOOKING_ATTENDANCE','CHECKIN'),('NO_SHOW','NO_SHOW_CONFIRMED'),
    ('MEMBERSHIP_PURCHASE','CHECKOUT_CREATED'),('MEMBERSHIP_ACTIVATION','MEMBERSHIP_ACTIVATED'),('MULTI_GYM_VISIT','CHECKIN')])
def test_distinct_selection_contexts_use_stored_source_evidence(configured_api,context,instant):
    from app.models.membership import UserMembership
    from app.models.access import AccessQrToken,Checkin,CustomerDailyAccess
    body=payload();contract=AccountingPolicy().model_dump(mode='json')
    contract['selection'][context]={'instant':instant,'approval':{'status':'APPROVED','reference':'Explicit context policy'}}
    body['terms']['policy_contract']=contract
    response=post(configured_api,body);assert response.status_code==200,response.text
    at=(NOW+timedelta(days=2)).replace(tzinfo=None)
    with Session(configured_api[2]) as db:
        checkout=PaymentCheckout(id=str(uuid4()),user_id=3,source_key=str(uuid4()),kind='BOOKING' if context in {'BOOKING_ATTENDANCE','NO_SHOW'} else 'MULTI_GYM',
            mode='test',provider='RAZORPAY',key_id='fixture',amount=150,currency='INR',snapshot={},status='PAID',created_at=at)
        db.add(checkout);db.flush()
        args=dict(checkout_id=checkout.id,context=context,selection_policy_version_id=response.json()['id'])
        if context in {'BOOKING_ATTENDANCE','NO_SHOW'}:
            booking=Booking(user_id=3,gym_id=1,gym_slot_id=1,slot_date=at.date(),quantity=1,unit_price=150,total_price=150,currency='INR',status='CONFIRMED',expires_at=at,checkout_id=checkout.id)
            if context=='NO_SHOW':booking.attendance_status='NO_SHOW';booking.attendance_marked_at=at
            db.add(booking);db.flush();args['booking_id']=booking.id
            if context=='BOOKING_ATTENDANCE':
                token=AccessQrToken(booking_id=booking.id,visitor_index=0,token_hash=str(uuid4()),valid_from=at-timedelta(hours=1),expires_at=at+timedelta(hours=1))
                db.add(token);db.flush()
                scan=Checkin(user_id=3,gym_id=1,qr_token_id=token.id,booking_id=booking.id,visitor_index=0,access_source='BOOKING_ACCESS',status='SUCCESS',checkin_time=at)
                db.add(scan);db.flush();args['checkin_id']=scan.id
        elif context!='MEMBERSHIP_PURCHASE':
            member=UserMembership(user_id=3,membership_type='MULTI_GYM',status='ACTIVE',start_at=at,end_at=at+timedelta(days=30),paid_amount=150,currency='INR',payment_status='PAID',gateway_checkout_id=checkout.id)
            db.add(member);db.flush()
            if context=='MULTI_GYM_VISIT':
                daily=CustomerDailyAccess(user_id=3,membership_id=member.id,access_type='MULTI_GYM',access_date=at.date(),access_key=str(uuid4()),status='USED',used_gym_id=1)
                db.add(daily);db.flush()
                token=AccessQrToken(daily_access_id=daily.id,token_hash=str(uuid4()),valid_from=at-timedelta(hours=1),expires_at=at+timedelta(hours=1))
                db.add(token);db.flush()
                scan=Checkin(user_id=3,gym_id=1,qr_token_id=token.id,daily_access_id=daily.id,membership_id=member.id,access_source='MEMBERSHIP_ACCESS',status='SUCCESS',checkin_time=at)
                db.add(scan);db.flush();args['checkin_id']=scan.id
        db.commit()
        selected=select_for_source(db,**args)
        assert selected['selected_at']==at and selected['evidence']['selection_instant']==instant
        assert selected['agreement_version_id']==response.json()['id']
        assert not selected['posting_eligible']
        if context=='MULTI_GYM_VISIT':
            token.valid_from=None;db.commit()
            with pytest.raises(HTTPException) as error:select_for_source(db,**args)
            assert error.value.detail['code']=='SOURCE_DATA_MISSING'