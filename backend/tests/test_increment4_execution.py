from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.auth import Role,UserRole
from app.models.access import Checkin
from app.models.gym_visit_payout import GymVisitPayout,GymMonthlyCalculation
from app.models.financial_review import FinancialReviewEvent
from app.models.source_evidence import SourceEvidence
from app.schemas.financial_review import ReviewCreate,ReviewDecision,ReviewExecution
from app.services import financial_reviews as reviews,gym_visit_payouts as visits,source_evidence
from app.services.marketplace_calculation import AllocationBlocked
from test_customer_policy_mysql import database
from test_increment2_mysql import prepare_month
from test_marketplace_booking_mysql import gates


@pytest.fixture
def approved(database,monkeypatch):
    engine,now,events,ids=prepare_month(database,monkeypatch,wallet=True)
    with Session(engine) as db:
        role=Role(name='ADMIN');db.add(role);db.flush()
        for uid in (2,3):db.add(UserRole(user_id=uid,role_id=role.id))
        db.flush();month=visits.finalize_month(db,mode='test',gym_id=1,period=now.date().replace(day=1));db.commit()
        visit=db.get(GymVisitPayout,ids[0]);db.get(Checkin,visit.checkin_id).status='REJECTED';db.flush()
        evidence=source_evidence.invalidated_multi_gym_visit(db,visit.checkin_id,3,'Verified source invalidation');db.commit()
        row=reviews.create(db,3,ReviewCreate(mode='test',gym_id=1,source_evidence_id=evidence.id,kind='MONTH_CORRECTION',reason='Monthly correction review'),'open-execution-review');db.commit()
        current=reviews.impact(db,evidence,1)
        decision=ReviewDecision(mode='test',expected_revision=1,status='APPROVED_FOR_RECONCILIATION',reason='Independent review approved',
            acknowledge_no_execution=True,acknowledge_reserved_paid=False,expected_impact_hash=reviews.digest(current))
        approval=reviews.decide(db,2,row.case_id,decision,'approve-execution-review');db.commit()
        assert db.scalar(select(func.count(GymMonthlyCalculation.id)))==1
        body=ReviewExecution(mode='test',expected_revision=2,expected_impact_hash=reviews.digest(current),
            authorization_reference='Explicit isolated execution authorization',reason='Append reviewed monthly invalidation',authorize_execution=True)
        return engine,now,row.case_id,body,month.id


def test_explicit_execution_appends_revision_and_audit_atomically(approved):
    engine,now,case,body,original_id=approved
    with Session(engine) as db:
        original=db.get(GymMonthlyCalculation,original_id);fingerprint=original.snapshot_hash
        row=reviews.execute(db,2,case,body,'execute-monthly-key');db.commit()
        assert row.status=='EXECUTED' and row.revision==3
        correction=db.get(GymMonthlyCalculation,row.snapshot['monthly_calculation_id'])
        assert correction.revision==2 and correction.gross_amount==60
        assert original.gross_amount==90 and original.snapshot_hash==fingerprint
        assert reviews.execute(db,2,case,body,'execute-monthly-key').id==row.id
        assert db.scalar(select(func.count(GymMonthlyCalculation.id)))==2
        assert db.scalar(select(func.count(FinancialReviewEvent.id)))==3


@pytest.mark.parametrize('flag',['source_evidence_enabled','marketplace_allocations_enabled'])
def test_execution_disabled_gates_never_write(approved,monkeypatch,flag):
    engine,now,case,body,original_id=approved
    monkeypatch.setattr(settings,flag,False)
    with Session(engine) as db:
        with pytest.raises(AllocationBlocked):reviews.execute(db,2,case,body,'disabled-execution-key')
        assert db.scalar(select(func.count(GymMonthlyCalculation.id)))==1
        assert reviews.latest(db,case).status=='APPROVED_FOR_RECONCILIATION'


def test_execution_stale_impact_and_missing_authorization_block(approved):
    engine,now,case,body,_=approved
    with Session(engine) as db:
        for changed,code in [(body.model_copy(update={'authorize_execution':False}),'EXECUTION_AUTHORIZATION_REQUIRED'),
            (body.model_copy(update={'expected_impact_hash':'0'*64}),'IMPACT_CHANGED')]:
            with pytest.raises(AllocationBlocked) as error:reviews.execute(db,2,case,changed,uuid4().hex)
            assert error.value.code==code
        assert db.scalar(select(func.count(GymMonthlyCalculation.id)))==1


def test_concurrent_execution_is_once(approved):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    engine,now,case,body,_=approved;barrier=Barrier(2)
    def execute(_):
        with Session(engine) as db:
            db.scalar(select(func.count(FinancialReviewEvent.id)));barrier.wait(timeout=20)
            row=reviews.execute(db,2,case,body,'same-concurrent-execution');db.commit();return row.id
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(execute,range(2)))
    assert len(set(results))==1


def test_new_reservation_since_approval_blocks_execution(approved):
    from app.models.owner_payout import OwnerPayout,OwnerPayoutItem
    from app.core.time import stored_instant
    engine,now,case,body,_=approved
    with Session(engine) as db:
        visit=db.scalars(select(GymVisitPayout)).first()
        payout=OwnerPayout(id=str(uuid4()),mode='test',gym_id=1,owner_user_id=3,category='MULTI_GYM',period_start=now.date().replace(day=1),period_end=now.date(),
            entitlement_amount=30,deduction_amount=0,amount=30,currency='INR',status='PAID',version=1,requested_by=3,request_key=uuid4().hex,
            request_hash='0'*64,deductions=[],created_at=stored_instant(now))
        db.add(payout);db.flush();db.add(OwnerPayoutItem(id=str(uuid4()),payout_id=payout.id,visit_payout_id=visit.id,amount=30));db.commit()
        with pytest.raises(AllocationBlocked) as error:reviews.execute(db,2,case,body,'protected-execution-key')
        assert error.value.code=='IMPACT_CHANGED'
        assert db.scalar(select(func.count(GymMonthlyCalculation.id)))==1 and db.get(OwnerPayout,payout.id).status=='PAID'


def test_failure_after_append_rolls_back_month_and_audit(approved,monkeypatch):
    engine,now,case,body,_=approved
    original=visits.finalize_month
    def fail(*args,**kwargs):
        original(*args,**kwargs)
        raise RuntimeError('Injected failure before audit')
    monkeypatch.setattr(visits,'finalize_month',fail)
    with Session(engine) as db:
        with pytest.raises(RuntimeError,match='Injected'):reviews.execute(db,2,case,body,'rollback-execution-key')
        db.commit() # nested transaction must have rolled back even if caller commits
        assert db.scalar(select(func.count(GymMonthlyCalculation.id)))==1
        assert db.scalar(select(func.count(FinancialReviewEvent.id)))==2


def test_unauthorized_execution_and_live_mode_rejected(approved):
    from fastapi import HTTPException
    engine,now,case,body,_=approved
    with Session(engine) as db:
        with pytest.raises(HTTPException) as error:reviews.execute(db,1,case,body,'customer-execution')
        assert error.value.status_code==403
        with pytest.raises(AllocationBlocked) as error:reviews.execute(db,2,case,body.model_copy(update={'mode':'live'}),'live-execution')
        assert error.value.code=='LIVE_PROCESSING_DISABLED'


def test_execution_http_explicit_authorization_and_no_automatic_action(approved):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.database.session import get_db
    from app.core.security import create_access_token
    from app.routers.admin_financial_readiness import router
    engine,now,case,body,_=approved
    app=FastAPI();app.include_router(router,prefix='/api/v1/admin')
    def session():
        with Session(engine) as db:yield db
    app.dependency_overrides[get_db]=session
    path=f'/api/v1/admin/financial-reconciliation/reviews/{case}/execute'
    with TestClient(app) as client:
        headers={'Authorization':'Bearer '+create_access_token('2'),'Idempotency-Key':'http-execution-key'}
        assert client.post(path,json=body.model_dump(mode='json')).status_code==401
        denied=client.post(path,json=body.model_copy(update={'authorize_execution':False}).model_dump(mode='json'),headers=headers)
        assert denied.status_code==409
        response=client.post(path,json=body.model_dump(mode='json'),headers=headers)
        assert response.status_code==200,response.text
        assert response.json()['status']=='EXECUTED' and response.headers['cache-control']=='no-store'
        assert client.post(path,json=body.model_dump(mode='json'),headers=headers).json()['id']==response.json()['id']


def test_closed_fee_budget_added_since_approval_never_rewritten(approved):
    from app.models.gym_visit_payout import MembershipVisitFee
    engine,now,case,body,_=approved
    with Session(engine) as db:
        review=reviews.latest(db,case)
        # Fixture budget simulates a concurrent completed attribution, not a
        # production change. Execution must notice the new immutable impact.
        budget=MembershipVisitFee(id=str(uuid4()),checkout_id=review.checkout_id,fee_evidence_id=review.source_evidence_id,
            mode='test',actual_fee=Decimal('2.37'),snapshot={'visits':[]},snapshot_hash=reviews.digest({'visits':[]}),created_at=review.created_at)
        db.add(budget);db.commit();fingerprint=budget.snapshot_hash
        with pytest.raises(AllocationBlocked) as error:reviews.execute(db,2,case,body,'closed-budget-execute')
        assert error.value.code=='IMPACT_CHANGED'
        assert db.get(MembershipVisitFee,budget.id).snapshot_hash==fingerprint
        assert db.scalar(select(func.count(GymMonthlyCalculation.id)))==1


def test_different_execution_retry_payload_rejected(approved):
    engine,now,case,body,_=approved
    with Session(engine) as db:
        row=reviews.execute(db,2,case,body,'immutable-execute-key');db.commit()
        with pytest.raises(AllocationBlocked) as error:
            reviews.execute(db,2,case,body.model_copy(update={'reason':'Different execution purpose'}),'immutable-execute-key')
        assert error.value.code=='IDEMPOTENCY_CONFLICT'
        assert db.scalar(select(func.count(GymMonthlyCalculation.id)))==2