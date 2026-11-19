"""4A schema invariants on disposable MySQL. Not a production posting adapter."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from uuid import uuid4
import pytest
from sqlalchemy import select, func, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from app.core.time import stored_instant
from app.models.marketplace_allocation import MarketplaceAllocation
from app.models.financial_agreement import FinancialAgreementScope, FinancialAgreementVersion, FinancialAgreementPin
from app.models.source_evidence import SourceEvidence, SourceOutbox, GymOwnerEvidence
from app.models.payment_checkout import PaymentCheckout
from test_customer_policy_mysql import database
from allocation_migration_helper import allocation_migration


def seed(engine, now):
    at=stored_instant(now)
    with Session(engine) as db:
        checkout=PaymentCheckout(id=str(uuid4()),user_id=1,source_key=str(uuid4()),kind='BOOKING',provider='RAZORPAY',
            mode='test',key_id='fixture',amount=100,currency='INR',snapshot={},status='PAID',created_at=at)
        scope=FinancialAgreementScope(mode='test',scope_key='DEFAULT')
        db.add_all([checkout,scope]);db.flush()
        agreement=FinancialAgreementVersion(scope_id=scope.id,version=1,effective_from=at-timedelta(days=1),terms={},action='AGREEMENT',
            agreement_reference='fixture',reason='Schema fixture only',ca_status='PENDING',actor_id=3,request_key='schema-fixture',request_hash='0'*64,created_at=at)
        db.add(agreement);db.flush()
        pin=FinancialAgreementPin(checkout_id=checkout.id,context='BOOKING_ATTENDANCE',source_key='booking:1:visitor:0',mode='test',
            agreement_version_id=agreement.id,selection_policy_version_id=agreement.id,selected_at=at,evidence={},evidence_hash='0'*64,created_at=at)
        evidence=SourceEvidence(id=str(uuid4()),idempotency_key=uuid4().hex,event_type='BOOKING_VISITOR_ATTENDED',source_type='CHECKIN',
            source_id='fixture-checkin',checkout_id=checkout.id,mode='test',evidence_status='VERIFIED_SOURCE',occurred_at=at,created_at=at,payload={},payload_hash='0'*64)
        db.add_all([pin,evidence]);db.flush()
        outbox=SourceOutbox(id=str(uuid4()),evidence_id=evidence.id,idempotency_key=uuid4().hex,event_type=evidence.event_type,
            source_id=evidence.source_id,mode='test',occurred_at=at,created_at=at,status='AWAITING_POLICY',retry_count=0,
            available_at=at,binding_status='AWAITING_POLICY_RESOLUTION')
        owner=GymOwnerEvidence(id=str(uuid4()),evidence_id=evidence.id,gym_id=1,owner_user_id=3,observed_at=at,basis='LOCKED_SOURCE_MUTATION')
        db.add_all([outbox,owner]);db.commit()
        return dict(source_event_id=outbox.id,source_evidence_id=evidence.id,source_type='CHECKIN',source_record_id='fixture-checkin',
            allocation_key='visitor:0',idempotency_key=uuid4().hex,checkout_id=checkout.id,transaction_reference=checkout.id,
            mode='test',category='ATTENDED_BOOKING',gym_id=1,owner_user_id=3,owner_evidence_id=owner.id,customer_id=1,
            booking_id=1,visitor_index=0,agreement_pin_id=pin.id,agreement_version_id=agreement.id,agreement_version=1,
            price_amount=Decimal('100'),discount_amount=Decimal('0'),tax_amount=Decimal('0'),eligible_amount=Decimal('100'),
            customer_funded_amount=Decimal('100'),wallet_amount=Decimal('0'),gateway_amount=Decimal('100'),
            gateway_fee=Decimal('2'),gym_gateway_fee_share=Decimal('1'),fitigo_gateway_fee_share=Decimal('1'),
            gym_gross_share=Decimal('85'),fitigo_gross_commission=Decimal('15'),gym_owner_net_entitlement=Decimal('84'),
            fitigo_net_commission=Decimal('14'),currency='INR',fee_status='VERIFIED',calculation_status='CALCULATED',
            posting_status='POSTED',entry_kind='ORIGINAL',occurred_at=at,created_at=at,calculation_snapshot={},calculation_hash='0'*64)


def migrate(engine):
    with engine.begin() as c:
        migration=allocation_migration(c)
        migration.downgrade();migration.upgrade()


def test_migration_roundtrip_no_backfill_and_database_immutability(database):
    engine,now=database
    migrate(engine)
    values=seed(engine,now)
    with Session(engine) as db:
        assert db.scalar(select(func.count(MarketplaceAllocation.id)))==0
        row=MarketplaceAllocation(id=str(uuid4()),**values);db.add(row);db.commit();identifier=row.id
        row.fitigo_gross_commission=Decimal('16')
        with pytest.raises(ValueError,match='immutable'):db.commit()
        db.rollback();db.delete(db.get(MarketplaceAllocation,identifier))
        with pytest.raises(ValueError,match='immutable'):db.commit()
        db.rollback()
    for sql in ('UPDATE marketplace_allocations SET fitigo_gross_commission=16','DELETE FROM marketplace_allocations'):
        with engine.begin() as c:
            with pytest.raises(DBAPIError,match='immutable'):c.execute(text(sql))
    with engine.begin() as c:
        with pytest.raises(RuntimeError,match='history'):allocation_migration(c).downgrade()


@pytest.mark.parametrize('bad',[
    {'fitigo_gross_commission':Decimal('16')},{'gateway_fee':Decimal('3')},
    {'gym_owner_net_entitlement':Decimal('100')},{'wallet_amount':Decimal('1')},
    {'gym_gateway_fee_share':None},{'posting_status':'DRAFT'},{'mode':'sandbox'},
    {'entry_kind':'REVERSAL'},{'currency':'USD'}])
def test_database_rejects_unbalanced_or_invalid_records(database,bad):
    engine,now=database
    values=seed(engine,now)
    with Session(engine) as db:
        db.add(MarketplaceAllocation(id=str(uuid4()),**{**values,**bad}))
        with pytest.raises(DBAPIError):db.commit()
        db.rollback()
        assert db.scalar(select(func.count(MarketplaceAllocation.id)))==0


def test_missing_fee_is_null_and_full_reversal_is_append_only(database):
    engine,now=database
    migrate(engine)
    values=seed(engine,now)
    with Session(engine) as db:
        original=MarketplaceAllocation(id=str(uuid4()),**values);db.add(original);db.commit()
        reversal={**values,'allocation_key':'reverse:'+original.id,'idempotency_key':uuid4().hex,'entry_kind':'REVERSAL','reversal_of_id':original.id}
        for column in ('price_amount','discount_amount','tax_amount','eligible_amount','customer_funded_amount','wallet_amount',
            'gateway_amount','gateway_fee','gym_gateway_fee_share','fitigo_gateway_fee_share','gym_gross_share',
            'fitigo_gross_commission','gym_owner_net_entitlement','fitigo_net_commission'):
            reversal[column]=-reversal[column]
        db.add(MarketplaceAllocation(id=str(uuid4()),**reversal));db.commit()
        assert db.scalar(select(func.sum(MarketplaceAllocation.gym_owner_net_entitlement)))==0
        db.add(MarketplaceAllocation(id=str(uuid4()),**{**reversal,'idempotency_key':uuid4().hex,'allocation_key':'duplicate-reversal'}))
        with pytest.raises(IntegrityError):db.commit()
        db.rollback()


def test_unique_event_unit_under_concurrent_writers(database):
    engine,now=database
    values=seed(engine,now);barrier=Barrier(2)
    def insert(_):
        with Session(engine) as db:
            barrier.wait(timeout=20)
            db.add(MarketplaceAllocation(id=str(uuid4()),**{**values,'idempotency_key':uuid4().hex}))
            try:db.commit();return 'created'
            except IntegrityError:db.rollback();return 'duplicate'
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(insert,range(2)))
    assert sorted(results)==['created','duplicate']
    with Session(engine) as db:assert db.scalar(select(func.count(MarketplaceAllocation.id)))==1