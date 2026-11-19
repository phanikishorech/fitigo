"""Production adapters and webhook paths with mocked transports only."""
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.source_evidence import SourceEvidence, SourceOutbox
from app.models.payment_checkout import PaymentAttempt
from test_booking_access_qr import api as booking_api
from test_razorpay_payments import api as razorpay_api, checkout, verify, webhook, refresh
from test_cashfree_payments import api as cash_api, verify as cash_verify, webhook as cash_webhook


@pytest.fixture(autouse=True)
def evidence_on(monkeypatch):
    monkeypatch.setattr(settings, 'source_evidence_enabled', True)


def test_razorpay_capture_is_deduplicated_and_not_created_time(razorpay_api):
    record=checkout(razorpay_api)
    entity=razorpay_api[3].pay(record, created_at=1791600000, fee=236, tax=36)
    assert webhook(razorpay_api,entity).status_code==200
    assert webhook(razorpay_api,entity).status_code==200
    assert verify(razorpay_api,record,entity).status_code==200
    with Session(razorpay_api[2]) as db:
        row=db.scalars(select(SourceEvidence).where(SourceEvidence.event_type=='PAYMENT_CAPTURED')).one()
        assert row.occurred_at is None and row.created_at is not None
        assert row.payload['capture_timestamp_source']=='UNAVAILABLE'
        assert row.payload['fee_amount']=='2.36' and row.payload['fee_tax_amount']=='0.36'
        assert row.payload['fee_basis']=='INCLUDING_TAX'
        assert row.payload['provider_event_id']=='evt-1'
        assert db.scalar(select(func.count(SourceOutbox.id)).where(SourceOutbox.event_type=='PAYMENT_CAPTURED'))==1
        assert db.get(PaymentAttempt,row.payload['attempt_id']).checkout_id==record['id']


def test_cashfree_capture_completion_time_and_missing_fee(cash_api):
    record=checkout(cash_api)
    cash_api[3].pay(record,payment_time='2026-10-10T03:29:00Z',payment_completion_time='2026-10-10T03:30:00Z')
    assert cash_webhook(cash_api,record).status_code==200
    assert cash_webhook(cash_api,record).status_code==200
    assert cash_verify(cash_api,record).status_code==200
    with Session(cash_api[2]) as db:
        row=db.scalars(select(SourceEvidence).where(SourceEvidence.event_type=='PAYMENT_CAPTURED')).one()
        assert row.occurred_at==datetime(2026,10,10,3,30)
        assert row.payload['fee_amount'] is None and row.payload['fee_tax_amount'] is None
        assert row.mode=='test' and row.occurred_at!=row.created_at


def test_razorpay_individual_refunds_survive_duplicate_observations(razorpay_api):
    record=checkout(razorpay_api);entity=razorpay_api[3].pay(record)
    assert verify(razorpay_api,record,entity).status_code==200
    entity['amount_refunded']=2500
    razorpay_api[3].refunds=lambda payment_id:[{'id':'rfnd_test1','payment_id':payment_id,
        'amount':2500,'currency':'INR','status':'processed','created_at':1791600000}]
    assert refresh(razorpay_api,record).status_code==200
    assert refresh(razorpay_api,record).status_code==200
    with Session(razorpay_api[2]) as db:
        rows=list(db.scalars(select(SourceEvidence).where(SourceEvidence.event_type=='REFUND_CONFIRMED')))
        assert len(rows)==1 and rows[0].amount==Decimal('25') and rows[0].occurred_at is None
        assert rows[0].payload['provider_payment_id']==entity['id']


def test_authorized_is_not_captured(razorpay_api):
    record=checkout(razorpay_api);entity=razorpay_api[3].pay(record,status='authorized')
    assert verify(razorpay_api,record,entity).status_code==200
    with Session(razorpay_api[2]) as db:
        assert db.scalar(select(func.count(SourceEvidence.id)).where(SourceEvidence.event_type=='PAYMENT_CAPTURED'))==0
        assert db.scalar(select(SourceEvidence.event_type).where(SourceEvidence.event_type=='PAYMENT_AUTHORIZED'))=='PAYMENT_AUTHORIZED'


def test_cashfree_refund_processed_timestamp_and_dedup(cash_api):
    record=checkout(cash_api);payment=cash_api[3].pay(record)
    assert cash_verify(cash_api,record).status_code==200
    refund={'cf_refund_id':'refund-1','cf_payment_id':payment['cf_payment_id'], 'order_id':record['gateway_order_id'],
        'refund_amount':25,'refund_currency':'INR','refund_status':'SUCCESS',
        'created_at':'2026-10-10T04:00:00Z','processed_at':'2026-10-10T05:00:00Z'}
    cash_api[3].refunds[record['gateway_order_id']]=[refund,refund]
    assert cash_webhook(cash_api,record,event='REFUND_STATUS_WEBHOOK').status_code==200
    assert cash_webhook(cash_api,record,event='REFUND_STATUS_WEBHOOK').status_code==200
    with Session(cash_api[2]) as db:
        row=db.scalars(select(SourceEvidence).where(SourceEvidence.event_type=='REFUND_CONFIRMED')).one()
        assert row.amount==Decimal('25') and row.occurred_at==datetime(2026,10,10,5)


def test_gateway_membership_activation_is_source_atomic(razorpay_api):
    quote=razorpay_api[0].get('/api/v1/memberships/gyms/1/plans/1/wallet-quote',headers=razorpay_api[1][1]).json()
    record=checkout(razorpay_api,{'kind':'SINGLE_GYM','gym_id':1,'plan_id':1,'accepted_quote':quote['quote_token']})
    entity=razorpay_api[3].pay(record)
    assert verify(razorpay_api,record,entity).status_code==200
    assert verify(razorpay_api,record,entity).status_code==200
    with Session(razorpay_api[2]) as db:
        row=db.scalars(select(SourceEvidence).where(SourceEvidence.event_type=='MEMBERSHIP_ACTIVATED')).one()
        assert row.payload['owner_id_at_event']==2 and row.payload['original_purchaser_id']==1
        assert row.checkout_id==record['id'] and row.mode=='test'


@pytest.mark.parametrize('value',[None,'2026-10-10T03:30:00','not-a-time'])
def test_cashfree_unreliable_timestamp_is_not_filled(cash_api,value):
    record=checkout(cash_api);cash_api[3].pay(record,payment_completion_time=value)
    assert cash_verify(cash_api,record).status_code==200
    with Session(cash_api[2]) as db:
        assert db.scalar(select(SourceEvidence.occurred_at).where(SourceEvidence.event_type=='PAYMENT_CAPTURED')) is None


def test_outbox_insert_failure_rolls_back_capture_and_fulfillment(razorpay_api,monkeypatch):
    from app.services import payment_evidence
    from app.models.booking import Booking
    record=checkout(razorpay_api);entity=razorpay_api[3].pay(record)
    original=payment_evidence.snapshot
    def fail(db,kind,*args,**kwargs):
        if kind=='PAYMENT_CAPTURED':raise RuntimeError('Simulated outbox failure')
        return original(db,kind,*args,**kwargs)
    monkeypatch.setattr(payment_evidence,'snapshot',fail)
    with pytest.raises(RuntimeError,match='outbox failure'):
        verify(razorpay_api,record,entity)
    with Session(razorpay_api[2]) as db:
        assert db.scalar(select(func.count(PaymentAttempt.id)))==0
        assert db.get(Booking,record['booking_ids'][0]).status=='PENDING_PAYMENT'
    monkeypatch.setattr(payment_evidence,'snapshot',original)
    assert verify(razorpay_api,record,entity).status_code==200


def test_razorpay_unverified_captured_flag_does_not_emit_capture(razorpay_api):
    record=checkout(razorpay_api);entity=razorpay_api[3].pay(record,captured=False)
    assert verify(razorpay_api,record,entity).status_code==200
    with Session(razorpay_api[2]) as db:
        assert db.scalar(select(func.count(SourceEvidence.id)).where(SourceEvidence.event_type=='PAYMENT_CAPTURED'))==0