"""Source-driven 4B allocation and cancellation concurrency on isolated MySQL."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.time import stored_instant
from app.models.booking import Booking, Payment
from app.models.access import Checkin, AccessQrToken
from app.models.gym import Gym
from app.models.payment_checkout import PaymentCheckout, PaymentAttempt
from app.models.financial_agreement import FinancialAgreementScope, FinancialAgreementVersion, FinancialAgreementPin
from app.models.source_evidence import SourceEvidence, SourceOutbox
from app.models.marketplace_allocation import MarketplaceAllocation
from app.schemas.accounting_policy import AccountingPolicy
from app.services import source_evidence
from app.services.marketplace_allocations import allocate_event, digest
from app.services.marketplace_calculation import AllocationBlocked
from test_customer_policy_mysql import database
from test_marketplace_calculation import terms
from test_financial_agreements import payload


@pytest.fixture(autouse=True)
def gates(monkeypatch):
    monkeypatch.setattr(settings,'source_evidence_enabled',True)
    monkeypatch.setattr(settings,'marketplace_allocations_enabled',True)
    monkeypatch.setattr(settings,'marketplace_live_allocations_enabled',False)


def setup(engine,now,*,no_show=False,basis=True,fee='2.37',mode='test'):
    at=stored_instant(now)
    commercial=terms()
    commercial['marketplace_contract']['cancellation_reversal']='FULL_ORIGINAL_ALLOCATION'
    agreement_terms=payload()['terms'];agreement_terms['marketplace_contract']=commercial['marketplace_contract']
    policy=AccountingPolicy().model_dump(mode='json')
    context='NO_SHOW' if no_show else 'BOOKING_ATTENDANCE'
    policy['selection'][context]={'instant':'NO_SHOW_CONFIRMED' if no_show else 'CHECKIN',
        'approval':{'status':'APPROVED','reference':'Fixture approved instant'}}
    agreement_terms['policy_contract']=policy
    with Session(engine) as db:
        scope=FinancialAgreementScope(mode=mode,scope_key='DEFAULT');db.add(scope);db.flush()
        agreement=FinancialAgreementVersion(scope_id=scope.id,version=1,effective_from=at-timedelta(days=1),terms=agreement_terms,
            action='AGREEMENT',agreement_reference='Fixture commercial agreement',reason='Unit fixture',ca_status='PENDING',
            actor_id=3,request_key=uuid4().hex,request_hash='0'*64,created_at=at-timedelta(days=2))
        db.add(agreement)
        checkout=PaymentCheckout(id=str(uuid4()),user_id=1,source_key=uuid4().hex,kind='BOOKING',provider='RAZORPAY',mode=mode,
            key_id='fixture',amount=Decimal('300'),currency='INR',snapshot={},status='PAID',gateway_order_id='order_'+uuid4().hex,
            gateway_payment_id='pay_'+uuid4().hex,created_at=at-timedelta(hours=1))
        db.add(checkout);db.flush()
        booking=db.get(Booking,1);booking.checkout_id=checkout.id;booking.quantity=3;booking.total_price=Decimal('300');booking.visitor_names=['A','B','C']
        payment=db.scalar(select(Payment).where(Payment.booking_id==1));payment.amount=Decimal('300');payment.provider='RAZORPAY';payment.external_ref=checkout.gateway_payment_id
        db.add(PaymentAttempt(id=str(uuid4()),checkout_id=checkout.id,external_id=checkout.gateway_payment_id,status='SUCCESS',amount=Decimal('300'),currency='INR',refunded_amount=0))
        db.flush()
        details={'booking_id':1}
        if basis: details['transaction_basis']={'price_representation':'GROSS_BEFORE_DISCOUNT','price_amount':'300.00','discount_amount':'0.00','tax_amount':'0.00','currency':'INR'}
        source_evidence.snapshot(db,'BOOKING_PURCHASE_RECORDED','BOOKING_CHECKOUT',f'{checkout.id}:1',checkout=checkout,
            occurred_at=checkout.created_at,payload=details,gym_id=1,observe_owner=True)
        if fee is not None:
            source_evidence.snapshot(db,'PAYMENT_CAPTURED','PAYMENT_ATTEMPT',checkout.gateway_payment_id,checkout=checkout,
                payload={'provider_payment_id':checkout.gateway_payment_id,'verification_status':'VERIFIED',
                    'verification_source':'AUTHENTICATED_PROVIDER_FETCH','fee_amount':fee,'fee_basis':'INCLUDING_TAX','fee_tax_amount':'0.00'})
        event_ids=[]
        if no_show:
            booking.attendance_status='NO_SHOW';booking.attendance_marked_at=at
            source=source_evidence.snapshot(db,'BOOKING_NO_SHOW_CONFIRMED','BOOKING',1,checkout=checkout,occurred_at=at,gym_id=1,observe_owner=True,
                payload={'booking_id':1,'scope':'WHOLE_BOOKING','confirmation_status':'AUTHORIZED_CLOSED_WINDOW','actor_id':3,
                    'admission_end':(now-timedelta(minutes=1)).isoformat(),'visitor_indices':[0,1,2]})
            event_ids.append(db.scalar(select(SourceOutbox.id).where(SourceOutbox.evidence_id==source.id)))
        else:
            for index in (0,2):
                qr=AccessQrToken(booking_id=1,visitor_index=index,visitor_name=booking.visitor_names[index],token_hash=uuid4().hex,
                    valid_from=at-timedelta(minutes=5),expires_at=at+timedelta(minutes=5),status='USED')
                db.add(qr);db.flush()
                scan=Checkin(user_id=1,booking_id=1,visitor_index=index,visitor_name=booking.visitor_names[index],gym_id=1,
                    qr_token_id=qr.id,access_source='BOOKING_ACCESS',status='SUCCESS',checkin_time=at)
                db.add(scan);db.flush()
                source_evidence.attendance(db,scan,qr,booking=booking)
                source=db.scalar(select(SourceEvidence).where(SourceEvidence.event_type=='BOOKING_VISITOR_ATTENDED',SourceEvidence.source_id==str(scan.id)))
                event_ids.append(db.scalar(select(SourceOutbox.id).where(SourceOutbox.evidence_id==source.id)))
        db.commit()
        return event_ids,checkout.id


def test_partial_group_fee_budget_idempotency_and_historical_owner(database):
    engine,now=database;ids,cid=setup(engine,now)
    with Session(engine) as db:
        db.get(Gym,1).owner_user_id=2;db.commit()
        first=allocate_event(db,ids[0]);db.commit()
        assert first[0].eligible_amount==100 and first[0].gym_gross_share==85
        assert first[0].gateway_fee==Decimal('0.80') and first[0].owner_user_id==3
        assert allocate_event(db,ids[0])[0].id==first[0].id;db.commit()
        allocate_event(db,ids[1]);db.commit()
        assert db.scalar(select(func.count(MarketplaceAllocation.id)))==2
        assert db.scalar(select(func.sum(MarketplaceAllocation.eligible_amount)))==200
        assert db.scalar(select(func.sum(MarketplaceAllocation.gateway_fee)))==Decimal('1.58')
        assert db.scalar(select(func.sum(MarketplaceAllocation.fitigo_gross_commission)))==30


def test_confirmed_whole_no_show_70_30(database):
    engine,now=database;ids,_=setup(engine,now,no_show=True)
    with Session(engine) as db:
        rows=allocate_event(db,ids[0]);db.commit()
        assert len(rows)==3 and sum(r.gym_gross_share for r in rows)==210
        assert sum(r.fitigo_gross_commission for r in rows)==90
        assert sum(r.gateway_fee for r in rows)==Decimal('2.37')
        assert sum(r.gym_gateway_fee_share for r in rows)==Decimal('1.18')
        assert sum(r.fitigo_gateway_fee_share for r in rows)==Decimal('1.19')


def test_missing_basis_blocks_without_pinning_or_partial_insert(database):
    engine,now=database;ids,_=setup(engine,now,basis=False)
    with Session(engine) as db:
        with pytest.raises(AllocationBlocked) as exc:allocate_event(db,ids[0])
        assert exc.value.code=='SOURCE_DATA_MISSING'
        db.commit()
        assert db.scalar(select(func.count(FinancialAgreementPin.id)))==0
        assert db.scalar(select(func.count(MarketplaceAllocation.id)))==0


def test_missing_fee_keeps_gross_and_unknown_net(database):
    engine,now=database;ids,_=setup(engine,now,fee=None)
    with Session(engine) as db:
        rows=allocate_event(db,ids[0]);db.commit()
        assert rows[0].gym_gross_share==85 and rows[0].gateway_fee is None
        assert rows[0].gym_owner_net_entitlement is None and rows[0].calculation_status=='FEE_PENDING'


def test_cancelled_booking_never_allocates(database):
    engine,now=database;ids,_=setup(engine,now)
    with Session(engine) as db:
        db.get(Booking,1).status='CANCELLED';db.commit()
        with pytest.raises(AllocationBlocked,match='Cancelled'):allocate_event(db,ids[0])
        db.rollback();assert db.scalar(select(func.count(MarketplaceAllocation.id)))==0


def test_live_is_never_automatically_enabled(database):
    engine,now=database;ids,_=setup(engine,now,mode='live')
    with Session(engine) as db:
        with pytest.raises(AllocationBlocked) as exc:allocate_event(db,ids[0])
        assert exc.value.code=='LIVE_PROCESSING_DISABLED'


def test_concurrent_duplicate_processing_same_source_is_once(database):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    engine,now=database;ids,_=setup(engine,now);barrier=Barrier(2)
    def process(_):
        with Session(engine) as db:
            barrier.wait(timeout=20)
            row=allocate_event(db,ids[0])[0];db.commit();return row.id
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(process,range(2)))
    assert len(set(results))==1
    with Session(engine) as db:assert db.scalar(select(func.count(MarketplaceAllocation.id)))==1


def test_late_fee_is_append_only_not_a_second_commission(database):
    from app.services.marketplace_corrections import apply_late_fee
    engine,now=database;ids,cid=setup(engine,now,fee=None)
    with Session(engine) as db:
        row=allocate_event(db,ids[0])[0];db.commit();identifier=row.id;old_hash=row.calculation_hash
        checkout=db.get(PaymentCheckout,cid)
        evidence=source_evidence.snapshot(db,'PAYMENT_DETAILS_VERIFIED','PAYMENT_ATTEMPT',checkout.gateway_payment_id,
            checkout=checkout,payload={'provider_payment_id':checkout.gateway_payment_id,'verification_status':'VERIFIED',
                'verification_source':'AUTHENTICATED_PROVIDER_FETCH','fee_amount':'2.37','fee_basis':'INCLUDING_TAX'})
        db.commit()
        event_id=db.scalar(select(SourceOutbox.id).where(SourceOutbox.evidence_id==evidence.id))
        adjustment=apply_late_fee(db,identifier,event_id);db.commit()
        assert adjustment.gym_gross_share==adjustment.fitigo_gross_commission==0
        assert adjustment.gym_gateway_fee_share==Decimal('0.40') and adjustment.fitigo_gateway_fee_share==Decimal('0.40')
        assert adjustment.gym_owner_net_entitlement==Decimal('-0.40')
        assert apply_late_fee(db,identifier,event_id).id==adjustment.id;db.commit()
        db.expire_all()
        assert db.get(MarketplaceAllocation,identifier).calculation_hash==old_hash
        assert db.get(MarketplaceAllocation,identifier).gateway_fee is None
        assert db.scalar(select(func.sum(MarketplaceAllocation.fitigo_gross_commission)))==15


def test_cancelled_source_full_reversal_and_retry_do_not_edit_original(database):
    from app.services.marketplace_corrections import reverse_cancelled
    engine,now=database;ids,cid=setup(engine,now)
    with Session(engine) as db:
        original=allocate_event(db,ids[0])[0];db.commit();identifier=original.id
        booking=db.get(Booking,1);booking.status='CANCELLED';booking.cancelled_at=stored_instant(now)
        source=source_evidence.snapshot(db,'BOOKING_CANCELLED','BOOKING_ADMIN_CANCELLATION',1,
            checkout=db.get(PaymentCheckout,cid),occurred_at=booking.cancelled_at,payload={'booking_id':1,'credit_status':'NO_CREDIT'})
        db.commit()
        event_id=db.scalar(select(SourceOutbox.id).where(SourceOutbox.evidence_id==source.id))
        reversal=reverse_cancelled(db,identifier,event_id);db.commit()
        assert reversal.reversal_of_id==identifier and reversal.gym_gross_share==-85
        assert reverse_cancelled(db,identifier,event_id).id==reversal.id;db.commit()
        assert db.scalar(select(func.sum(MarketplaceAllocation.gym_owner_net_entitlement)))==0
        assert db.scalar(select(func.sum(MarketplaceAllocation.fitigo_gross_commission)))==0


def test_allocation_vs_cancellation_serializes_on_same_booking(database):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.services.admin_booking_ops_service import AdminBookingOpsService
    engine,now=database;ids,_=setup(engine,now,no_show=True)
    # Existing no-show evidence closes the booking. The production cancellation
    # operation must reject it, rather than race an allocation into cancelled value.
    barrier=Barrier(2)
    def process():
        with Session(engine) as db:
            barrier.wait(timeout=20)
            rows=allocate_event(db,ids[0]);db.commit();return len(rows)
    def cancel():
        from fastapi import HTTPException
        with Session(engine) as db:
            barrier.wait(timeout=20)
            try:AdminBookingOpsService(db).cancel_booking(booking_id=1,actor_id=3)
            except HTTPException:db.rollback();return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(process);b=pool.submit(cancel)
        assert a.result(timeout=30)==3 and b.result(timeout=30)=='rejected'
    with Session(engine) as db:assert db.get(Booking,1).status=='CONFIRMED'