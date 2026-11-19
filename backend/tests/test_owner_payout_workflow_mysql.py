from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.time import as_ist,stored_instant
from app.models.auth import Role,UserRole
from app.models.owner_payout import OwnerPayout,OwnerPayoutAudit
from app.schemas.owner_payout import PayoutCreate,PayoutTransition
from app.services import owner_payouts
from app.services.marketplace_calculation import AllocationBlocked
from test_customer_policy_mysql import database
from test_marketplace_allocation_mysql import seed
from app.models.marketplace_allocation import MarketplaceAllocation
from app.models.financial_agreement import FinancialAgreementVersion


@pytest.fixture
def prepared(database,monkeypatch):
    engine,now=database
    monkeypatch.setattr(settings,'marketplace_payouts_enabled',True)
    monkeypatch.setattr(owner_payouts,'utcnow',lambda:now+timedelta(days=40))
    values=seed(engine,now)
    from app.schemas.accounting_policy import SettlementPolicy
    settlement={'approval':{'status':'APPROVED','reference':'Fixture approved settlement'},'weekly_cutoff_day':0,
        'monthly_cutoff_day':1,'short_month':'LAST_CALENDAR_DAY','cutoff_time':'12:00:00','timezone':'Asia/Kolkata',
        'holding_days':0,'eligible_deductions':[],'partial_settlement':'ALLOW_WITH_ALLOCATION_LINKS',
        'failed_settlement':'REMAIN_OUTSTANDING_REQUIRE_EVIDENCE'}
    from app.services.marketplace_allocations import digest
    with Session(engine) as db:
        role=Role(name='ADMIN');db.add(role);db.flush();db.add(UserRole(user_id=3,role_id=role.id))
        # Fixture-only direct SQL before allocation; no production agreement edit.
        from sqlalchemy import update
        db.execute(update(FinancialAgreementVersion).where(FinancialAgreementVersion.id==values['agreement_version_id']).values(
            terms={'settlements':{'booking_cycle':'WEEKLY','minimum_payout':'1.00'},'policy_contract':{'settlements':settlement}}))
        snapshot={'policy':{'fee_before_payout':'REQUIRED'}}
        row=MarketplaceAllocation(id=str(uuid4()),**{**values,'category':'SINGLE_GYM','calculation_snapshot':snapshot,'calculation_hash':digest(snapshot)})
        db.add(row);db.commit();identifier=row.id
    return engine,now,identifier


def request(identifier,amount='84'):
    return PayoutCreate(items=[{'allocation_id':identifier,'amount':amount}],reason='Verified owner entitlement')


def move(db,row,status,key='step-key',evidence=None):
    return owner_payouts.transition(db,3,row.id,PayoutTransition(expected_version=row.version,status=status,
        reason='Admin reviewed source evidence',payment_evidence=evidence),key)


def test_approval_not_paid_actual_evidence_required(prepared):
    engine,now,identifier=prepared
    with Session(engine) as db:
        row=owner_payouts.create(db,3,request(identifier),'create-key');db.commit()
        assert row.status=='PENDING_APPROVAL' and row.paid_at is None
        assert owner_payouts.create(db,3,request(identifier),'create-key').id==row.id;db.commit()
        move(db,row,'APPROVED','approve-key');db.commit()
        assert row.paid_at is None and row.payment_reference is None
        move(db,row,'PROCESSING','processing-key');db.commit()
        with pytest.raises(AllocationBlocked):move(db,row,'PAID','missing-evidence-key')
        db.rollback()
        evidence={'reference':'BANK-123','paid_at':(now+timedelta(days=40)).isoformat(),'amount':'84','currency':'INR',
            'source':'BANK_STATEMENT','document_reference':'Protected bank document 1','owner_user_id':3}
        move(db,row,'PAID','paid-key',evidence);db.commit()
        assert row.status=='PAID' and row.payment_reference=='BANK-123'
        assert db.scalar(select(func.count(OwnerPayoutAudit.id)))==4
        with pytest.raises(AllocationBlocked):owner_payouts.create(db,3,request(identifier),'new-create-key')
        db.rollback()


def test_failed_payout_retains_reservation_and_retry(prepared):
    engine,now,identifier=prepared
    with Session(engine) as db:
        row=owner_payouts.create(db,3,request(identifier),'create-key');db.commit()
        for status in ('APPROVED','PROCESSING','FAILED'):
            move(db,row,status,status+'-key');db.commit()
        assert row.status=='FAILED' and row.paid_at is None
        with pytest.raises(AllocationBlocked):owner_payouts.create(db,3,request(identifier),'duplicate-pay-key')
        db.rollback()
        move(db,row,'PENDING_APPROVAL','retry-key');db.commit()
        assert row.status=='PENDING_APPROVAL'


def test_concurrent_reservations_cannot_exceed_entitlement(prepared):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    engine,now,identifier=prepared;barrier=Barrier(2)
    def reserve(key):
        with Session(engine) as db:
            barrier.wait(timeout=20)
            try:owner_payouts.create(db,3,request(identifier,'60'),key);db.commit();return 'reserved'
            except AllocationBlocked:db.rollback();return 'blocked'
    with ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(reserve,['first-key','second-key']))
    assert sorted(result)==['blocked','reserved']
    with Session(engine) as db:assert db.scalar(select(func.sum(OwnerPayout.entitlement_amount)))==60


def test_unauthorized_and_unapproved_deductions_rejected(prepared):
    engine,now,identifier=prepared
    with Session(engine) as db:
        with pytest.raises(HTTPException):owner_payouts.create(db,1,request(identifier),'unauthorized-key')
        body=PayoutCreate(items=[{'allocation_id':identifier,'amount':'84'}],reason='Deduction request',deductions=[{
            'kind':'ACTUAL_TAX_WITHHOLDING','amount':'1','reason':'Evidence reason','evidence_reference':'document'}])
        with pytest.raises(AllocationBlocked):owner_payouts.create(db,3,body,'deduction-key')
        db.rollback();assert db.scalar(select(func.count(OwnerPayout.id)))==0


def test_cancel_unpaid_request_releases_reservation(prepared):
    engine,now,identifier=prepared
    with Session(engine) as db:
        row=owner_payouts.create(db,3,request(identifier),'create-key');db.commit()
        move(db,row,'REVERSED','cancel-key');db.commit()
        again=owner_payouts.create(db,3,request(identifier),'new-key');db.commit()
        assert again.id!=row.id and again.amount==84


def test_source_refund_after_approval_blocks_paid_transition(prepared):
    from app.models.payment_checkout import PaymentCheckout
    engine,now,identifier=prepared
    with Session(engine) as db:
        row=owner_payouts.create(db,3,request(identifier),'refund-create-key');db.commit()
        move(db,row,'APPROVED','refund-approve');db.commit()
        source=db.get(MarketplaceAllocation,identifier)
        db.get(PaymentCheckout,source.checkout_id).status='REFUNDED';db.commit()
        with pytest.raises(AllocationBlocked):move(db,row,'PROCESSING','refund-processing')
        db.rollback();assert db.get(OwnerPayout,row.id).status=='APPROVED'


def test_paid_return_requires_distinct_evidence_and_preserves_outgoing_reference(prepared):
    from app.services.marketplace_reporting import report
    engine,now,identifier=prepared
    with Session(engine) as db:
        row=owner_payouts.create(db,3,request(identifier),'return-create-key');db.commit()
        move(db,row,'APPROVED','return-approve');db.commit();move(db,row,'PROCESSING','return-processing');db.commit()
        actual={'reference':'PAY-RETURN-TEST','paid_at':(now+timedelta(days=40)).isoformat(),'amount':'84','currency':'INR',
            'source':'BANK_STATEMENT','document_reference':'Protected outgoing evidence','owner_user_id':3}
        move(db,row,'PAID','return-paid',actual);db.commit()
        with pytest.raises(AllocationBlocked):move(db,row,'REVERSED','return-missing')
        db.rollback()
        returned={**actual,'reference':'RETURN-TEST','document_reference':'Protected actual bank return'}
        move(db,row,'REVERSED','return-confirmed',returned);db.commit()
        assert row.payment_reference=='PAY-RETURN-TEST' and row.status=='REVERSED'
        report_day=(now+timedelta(days=40)).date()
        data=report(db,mode='test',date_from=report_day,date_to=report_day)
        assert data['totals']['actual_payouts_made']=='84.00' and data['totals']['actual_payout_returns']=='84.00'