from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func,event,update,text,inspect
from sqlalchemy.orm import Session
from app.models.financial_review import FinancialReviewEvent
from app.models.source_evidence import SourceEvidence
from app.models.marketplace_allocation import MarketplaceAllocation
from app.models.financial_agreement import FinancialAgreementVersion
from app.models.owner_payout import OwnerPayout
from app.schemas.financial_review import ReviewCreate,ReviewDecision
from app.services import financial_readiness as readiness,financial_reviews as reviews,owner_payouts
from app.services.marketplace_allocations import digest
from app.services.marketplace_calculation import AllocationBlocked
from test_customer_policy_mysql import database
from test_owner_payout_workflow_mysql import prepared,request as payout_request,move
from test_increment3_readiness import settlement
from test_financial_agreements import configured_api,mysql_api,pytestmark


def test_admin_report_authorization_and_get_is_read_only(configured_api):
    client,headers,engine=configured_api
    path='/api/v1/admin/financial-reconciliation?mode=test&view=sources'
    assert client.get(path).status_code==401
    assert client.get(path,headers=headers[1]).status_code==403
    writes=[]
    def spy(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')):writes.append(statement)
    event.listen(engine,'before_cursor_execute',spy)
    try:
        for view in ('individual','single_gym','no_show','multi_gym','fees','sources','collections','balances','corrections'):
            response=client.get(path.replace('sources',view),headers=headers[5])
            assert response.status_code==200,response.text
            assert response.json()['read_only'] is True
            assert response.json()['controls']['activation_authorized'] is False
            assert response.headers['cache-control']=='no-store'
        assert writes==[]
    finally:event.remove(engine,'before_cursor_execute',spy)


def test_missing_schema_reports_absent_not_zero(configured_api,monkeypatch):
    original=readiness.TABLES
    monkeypatch.setattr(readiness,'TABLES',(*original,'not_deployed_fixture'))
    with Session(configured_api[2]) as db:
        result=readiness.report(db,mode='test',view='sources')
        assert result['available'] is False and result['page_totals']=={}


def commercialize(db,identifier,policy):
    from app.services.gym_financial_settings import defaults
    allocation=db.get(MarketplaceAllocation,identifier)
    raw=defaults();raw['settlements']=policy
    db.execute(update(FinancialAgreementVersion).where(FinancialAgreementVersion.id==allocation.agreement_version_id).values(terms={'financial_settings':raw}))
    db.flush();db.expire_all()


def test_pinned_settlement_missing_and_complete_policy(prepared):
    engine,now,identifier=prepared
    with Session(engine) as db:
        commercialize(db,identifier,{})
        with pytest.raises(AllocationBlocked) as error:owner_payouts.financial_position(db,db.get(MarketplaceAllocation,identifier))
        assert error.value.code=='SETTLEMENT_TIMING_UNCONFIGURED'
        commercialize(db,identifier,settlement());db.commit()
        pos=owner_payouts.financial_position(db,db.get(MarketplaceAllocation,identifier),now=now+timedelta(days=40))
        assert pos['status']=='AVAILABLE' and pos['entitlement']==84
        row=owner_payouts.create(db,3,payout_request(identifier),'commercial-payout-key');db.commit()
        assert row.status=='PENDING_APPROVAL' and row.payment_reference is None
        data=readiness.report(db,mode='test',view='balances')
        assert data['page_totals']['reserved_entitlement']=='84.00'
        assert data['page_totals']['actual_paid']=='0.00'
        assert data['items'][0]['trace']['items'][0]['allocation_id']==identifier


def add_second_admin(db):
    from app.models.auth import Role,UserRole
    role=db.scalar(select(Role).where(Role.name=='ADMIN'))
    db.add(UserRole(user_id=2,role_id=role.id));db.flush()


def test_reserved_review_append_only_independent_approval_no_adjustment(prepared):
    engine,now,identifier=prepared
    with Session(engine) as db:
        payout=owner_payouts.create(db,3,payout_request(identifier),'reserved-fixture');db.commit()
        original=db.get(MarketplaceAllocation,identifier)
        source=db.get(SourceEvidence,original.source_evidence_id)
        # Seed helper evidence lacks the original gym field; set fixture before opening review.
        payload={**source.payload,'gym_id':1}
        db.execute(update(SourceEvidence).where(SourceEvidence.id==source.id).values(payload=payload,payload_hash=digest(payload)))
        add_second_admin(db);db.commit();db.expire_all()
        body=ReviewCreate(mode='test',gym_id=1,source_evidence_id=source.id,kind='RESERVED_OR_PAID',reason='Review disputed protected amount')
        row=reviews.create(db,3,body,'open-review-key');db.commit()
        assert reviews.create(db,3,body,'open-review-key').id==row.id
        impact=reviews.impact(db,db.get(SourceEvidence,source.id),1)
        decision=dict(mode='test',expected_revision=1,status='APPROVED_FOR_RECONCILIATION',reason='Independent review completed',
            acknowledge_no_execution=True,acknowledge_reserved_paid=False,expected_impact_hash=digest(impact))
        with pytest.raises(AllocationBlocked) as error:reviews.decide(db,2,row.case_id,ReviewDecision(**decision),'decision-missing-ack')
        assert error.value.code=='PROTECTED_AMOUNT_REVIEW_REQUIRED'
        decision['acknowledge_reserved_paid']=True
        with pytest.raises(AllocationBlocked) as error:reviews.decide(db,3,row.case_id,ReviewDecision(**decision),'same-actor-key')
        assert error.value.code=='INDEPENDENT_REVIEW_REQUIRED'
        approval=reviews.decide(db,2,row.case_id,ReviewDecision(**decision),'approval-key');db.commit()
        assert approval.revision==2 and db.scalar(select(func.count(FinancialReviewEvent.id)))==2
        assert db.get(OwnerPayout,payout.id).status=='PENDING_APPROVAL'
        assert db.scalar(select(func.count(MarketplaceAllocation.id)))==1
        with pytest.raises(AllocationBlocked) as error:owner_payouts.financial_position(db,original)
        assert error.value.code=='FINANCIAL_REVIEW_OPEN'
        row.reason='rewrite'
        with pytest.raises(ValueError,match='append-only'):db.flush()
        db.rollback()


def test_report_conserves_allocation_amounts_and_environment(prepared):
    engine,now,identifier=prepared
    with Session(engine) as db:
        result=readiness.report(db,mode='test',view='single_gym')
        assert result['total']==1 and result['items'][0]['differences']==[]
        assert Decimal(result['page_totals']['gross_entitlement'])-Decimal(result['page_totals']['gym_fee'])==Decimal(result['page_totals']['net_payable'])
        assert readiness.report(db,mode='live',view='single_gym')['total']==0


def test_review_api_rejects_non_admin(configured_api):
    client,headers,engine=configured_api
    body={'mode':'test','gym_id':1,'source_evidence_id':str(uuid4()),'kind':'LATE_VISIT','reason':'Source review'}
    for actor,expected in [(1,403),(5,404)]:
        response=client.post('/api/v1/admin/financial-reconciliation/reviews',json=body,headers={**headers[actor],'Idempotency-Key':'review-api-test'})
        assert response.status_code==expected,response.text


def test_forward_review_migration_on_disposable_runner():
    from app.database.session import engine
    assert engine.url.database.startswith('fitigo_test_')
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version'))=='eb3f70126935'
        assert inspect(connection).has_table('financial_review_events')
        names=set(connection.scalars(text("SELECT TRIGGER_NAME FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE() AND EVENT_OBJECT_TABLE='financial_review_events'")))
        assert names=={'financial_review_events_no_update','financial_review_events_no_delete'}


def test_future_settlement_change_preserves_checkout_pinned_policy(prepared):
    engine,now,identifier=prepared
    with Session(engine) as db:
        commercialize(db,identifier,settlement());db.commit()
        allocation=db.get(MarketplaceAllocation,identifier)
        original=db.get(FinancialAgreementVersion,allocation.agreement_version_id)
        terms=dict(original.terms);terms['financial_settings']={**terms['financial_settings'],'settlements':{**settlement(),'holding_days':100}}
        from app.core.time import stored_instant
        newer=FinancialAgreementVersion(scope_id=original.scope_id,version=2,effective_from=stored_instant(now)+timedelta(days=1),terms=terms,
            action='AGREEMENT',agreement_reference='Future settlement',reason='Explicit later holding policy',ca_status='PENDING',actor_id=3,
            request_key=uuid4().hex,request_hash='0'*64,created_at=stored_instant(now))
        db.add(newer);db.commit()
        pos=owner_payouts.financial_position(db,allocation,now=now+timedelta(days=40))
        assert pos['status']=='AVAILABLE' and pos['policy'].holding_days==2
        assert allocation.agreement_version_id==original.id


def test_tax_report_unknown_zero_nonzero_and_snapshot_unchanged(prepared):
    engine,now,identifier=prepared
    with Session(engine) as db:
        original=db.get(MarketplaceAllocation,identifier)
        checkout_id=original.checkout_id
        from app.models.booking import Booking
        db.get(Booking,1).checkout_id=checkout_id
        payload={'booking_id':1,'gym_id':1,'financial_configuration':{'status':'PINNED'},
            'transaction_basis':{'price_amount':'100','discount_amount':'0','tax_amount':None,'currency':'INR','price_representation':'GROSS_BEFORE_DISCOUNT'}}
        source=SourceEvidence(id=str(uuid4()),idempotency_key=uuid4().hex,event_type='BOOKING_PURCHASE_RECORDED',source_type='BOOKING_CHECKOUT',
            source_id=checkout_id+':1',checkout_id=checkout_id,mode='test',evidence_status='VERIFIED_SOURCE',
            occurred_at=original.occurred_at,created_at=original.occurred_at,payload=payload,payload_hash=digest(payload))
        db.add(source);db.commit();saved=original.calculation_hash
        data=readiness.report(db,mode='test',view='sources')
        assert data['items'][0]['tax']['status']=='UNKNOWN' and data['items'][0]['percentage_allocation_blocked']
        assert db.get(MarketplaceAllocation,identifier).calculation_hash==saved
        assert data['items'][0]['trace']['source_evidence_ids']==[source.id]


def test_review_change_conflict_and_rejection_does_not_mutate_finances(prepared):
    engine,now,identifier=prepared
    with Session(engine) as db:
        original=db.get(MarketplaceAllocation,identifier);source=db.get(SourceEvidence,original.source_evidence_id)
        payload={**source.payload,'gym_id':1};db.execute(update(SourceEvidence).where(SourceEvidence.id==source.id).values(payload=payload,payload_hash=digest(payload)));db.commit();db.expire_all()
        # A generic protected review requires a real reservation.
        payout=owner_payouts.create(db,3,payout_request(identifier),'review-reservation');db.commit()
        body=ReviewCreate(mode='test',gym_id=1,source_evidence_id=source.id,kind='RESERVED_OR_PAID',reason='Review request')
        row=reviews.create(db,3,body,'review-create-conflict');db.commit()
        decision=ReviewDecision(mode='test',expected_revision=1,status='REJECTED',reason='No correction justified',
            acknowledge_no_execution=True,acknowledge_reserved_paid=True,expected_impact_hash='0'*64)
        with pytest.raises(AllocationBlocked) as error:reviews.decide(db,3,row.case_id,decision,'wrong-impact-key')
        assert error.value.code=='IMPACT_CHANGED'
        current=reviews.impact(db,db.get(SourceEvidence,source.id),1)
        decision=decision.model_copy(update={'expected_impact_hash':digest(current)})
        rejected=reviews.decide(db,3,row.case_id,decision,'reject-key');db.commit()
        assert rejected.status=='REJECTED'
        assert db.get(OwnerPayout,payout.id).status=='PENDING_APPROVAL'
        assert owner_payouts.financial_position(db,original)['reserved']==84


def test_concurrent_review_decisions_only_one_revision_wins(prepared):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    engine,now,identifier=prepared
    with Session(engine) as db:
        allocation=db.get(MarketplaceAllocation,identifier);source=db.get(SourceEvidence,allocation.source_evidence_id)
        payload={**source.payload,'gym_id':1};db.execute(update(SourceEvidence).where(SourceEvidence.id==source.id).values(payload=payload,payload_hash=digest(payload)))
        owner_payouts.create(db,3,payout_request(identifier),'race-reservation');db.commit();db.expire_all()
        review=reviews.create(db,3,ReviewCreate(mode='test',gym_id=1,source_evidence_id=source.id,kind='RESERVED_OR_PAID',reason='Concurrent review'), 'race-open');db.commit()
        case_id=review.case_id
        impact_hash=digest(reviews.impact(db,db.get(SourceEvidence,source.id),1))
    barrier=Barrier(2)
    def decide(key):
        with Session(engine) as db:
            db.scalar(select(func.count(FinancialReviewEvent.id)))
            barrier.wait(timeout=20)
            body=ReviewDecision(mode='test',expected_revision=1,status='NEEDS_EVIDENCE',reason='Need protected evidence',
                acknowledge_no_execution=True,acknowledge_reserved_paid=True,expected_impact_hash=impact_hash)
            try:row=reviews.decide(db,3,case_id,body,key);db.commit();return row.revision
            except AllocationBlocked as error:db.rollback();return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(decide,['race-decision-one','race-decision-two']))
    assert sorted(map(str,results))==['2','VERSION_CONFLICT']


def test_monthly_fee_reconciliation_late_visit_and_closed_budget_review(database,monkeypatch):
    from test_increment2_mysql import prepare_month
    from app.models.gym_visit_payout import GymVisitPayout,GymMonthlyCalculation,MembershipVisitFee
    from app.models.payment_checkout import PaymentCheckout
    from app.models.auth import Role,UserRole
    from app.services import gym_visit_payouts as visits,source_evidence
    from app.core.config import settings
    monkeypatch.setattr(settings,'source_evidence_enabled',True)
    monkeypatch.setattr(settings,'marketplace_allocations_enabled',True)
    engine,now,events,ids=prepare_month(database,monkeypatch)
    with Session(engine) as db:
        role=Role(name='ADMIN');db.add(role);db.flush();db.add(UserRole(user_id=3,role_id=role.id));db.flush()
        month=visits.finalize_month(db,mode='test',gym_id=1,period=now.date().replace(day=1));db.commit()
        visit=db.get(GymVisitPayout,ids[0]);checkout=db.get(PaymentCheckout,visit.checkout_id)
        source_evidence.snapshot(db,'PAYMENT_DETAILS_VERIFIED','PAYMENT_ATTEMPT',checkout.gateway_payment_id,checkout=checkout,
            payload={'provider_payment_id':checkout.gateway_payment_id,'verification_status':'VERIFIED','verification_source':'AUTHENTICATED_PROVIDER_FETCH','fee_amount':'2.37','fee_basis':'INCLUDING_TAX'})
        db.flush();budget=visits.attribute_membership_fee(db,checkout.id);db.commit()
        report=readiness.report(db,mode='test',view='fees')
        assert report['items'][0]['actual_provider_fee']=='2.37'
        assert report['items'][0]['unattributed_fee']=='0.00' and report['items'][0]['differences']==[]
        monthly=readiness.report(db,mode='test',view='multi_gym')
        assert monthly['page_totals']['gross_entitlement']=='90.00' and monthly['page_totals']['net_payable']=='90.00'
        assert all(row['fitigo_earnings'] is None for row in monthly['items'])
        collections=readiness.report(db,mode='test',view='collections')
        assert collections['items'][0]['unallocated_collection']=='100.00'
        assert visits.allocate_visit(db,events[0]).id==visit.id
        review=reviews.create(db,3,ReviewCreate(mode='test',gym_id=1,source_evidence_id=visit.source_evidence_id,
            kind='CLOSED_FEE_BUDGET',reason='Review membership allocation change'),'closed-fee-review');db.commit()
        assert review.snapshot['closed_fee_budgets'][0]['id']==budget.id
        assert db.scalar(select(func.count(MembershipVisitFee.id)))==1
        assert db.scalar(select(func.count(GymMonthlyCalculation.id)))==1
        assert month.gross_amount==90


def test_late_admission_review_does_not_bypass_final_month(database,monkeypatch):
    from test_increment2_mysql import prepare_month
    from app.models.gym_visit_payout import GymVisitPayout,GymMonthlyCalculation
    from app.models.auth import Role,UserRole
    from app.models.access import Checkin,AccessQrToken,CustomerDailyAccess
    from app.models.membership import UserMembership
    from app.models.source_evidence import SourceOutbox
    from app.services import gym_visit_payouts as visits,source_evidence
    from app.core.config import settings
    from app.core.time import stored_instant
    monkeypatch.setattr(settings,'source_evidence_enabled',True);monkeypatch.setattr(settings,'marketplace_allocations_enabled',True)
    engine,now,events,ids=prepare_month(database,monkeypatch,wallet=True)
    with Session(engine) as db:
        role=Role(name='ADMIN');db.add(role);db.flush();db.add(UserRole(user_id=3,role_id=role.id));db.flush()
        month=visits.finalize_month(db,mode='test',gym_id=1,period=now.date().replace(day=1));db.commit()
        member=db.get(UserMembership,1);stamp=stored_instant(now)+timedelta(days=4)
        daily=CustomerDailyAccess(user_id=1,membership_id=1,access_type='MULTI_GYM',access_date=stamp.date(),access_key=uuid4().hex,status='USED',used_gym_id=1)
        db.add(daily);db.flush();token=AccessQrToken(daily_access_id=daily.id,token_hash=uuid4().hex,valid_from=stamp-timedelta(minutes=1),expires_at=stamp+timedelta(minutes=1),status='USED')
        db.add(token);db.flush();scan=Checkin(user_id=1,gym_id=1,membership_id=1,daily_access_id=daily.id,qr_token_id=token.id,status='SUCCESS',checkin_time=stamp,access_source='MEMBERSHIP_ACCESS')
        db.add(scan);db.flush();daily.checkin_id=scan.id;token.checkin_id=scan.id
        source_evidence.attendance(db,scan,token,membership=member,daily=daily);db.flush()
        event_row=db.scalar(select(SourceOutbox).where(SourceOutbox.event_type=='MULTI_GYM_VISIT_VERIFIED',SourceOutbox.source_id==str(scan.id)));db.commit()
        with pytest.raises(AllocationBlocked) as error:visits.allocate_visit(db,event_row.id)
        assert error.value.code=='FINALIZED_MONTH_REVIEW'
        review=reviews.create(db,3,ReviewCreate(mode='test',gym_id=1,source_evidence_id=event_row.evidence_id,kind='LATE_VISIT',reason='Late admission needs review'),'late-admission-review');db.commit()
        assert review.snapshot['monthly_calculations'][0]['id']==month.id
        assert db.scalar(select(func.count(GymVisitPayout.id)))==3 and month.gross_amount==90


def test_paid_review_cannot_release_money_or_rewrite_payout(prepared):
    engine,now,identifier=prepared
    with Session(engine) as db:
        payout=owner_payouts.create(db,3,payout_request(identifier),'paid-review-fixture');db.commit()
        move(db,payout,'APPROVED','paid-review-approved');move(db,payout,'PROCESSING','paid-review-processing')
        evidence={'reference':'BANK-PAID-REVIEW','paid_at':(now+timedelta(days=40)).isoformat(),'amount':'84','currency':'INR',
            'source':'BANK_STATEMENT','document_reference':'Protected bank evidence','owner_user_id':3}
        move(db,payout,'PAID','paid-review-paid',evidence);db.commit()
        allocation=db.get(MarketplaceAllocation,identifier);source=db.get(SourceEvidence,allocation.source_evidence_id)
        payload={**source.payload,'gym_id':1};db.execute(update(SourceEvidence).where(SourceEvidence.id==source.id).values(payload=payload,payload_hash=digest(payload)));db.commit();db.expire_all()
        review=reviews.create(db,3,ReviewCreate(mode='test',gym_id=1,source_evidence_id=source.id,kind='RESERVED_OR_PAID',reason='Disputed paid amount review'),'paid-review-open');db.commit()
        assert review.snapshot['protected_claims'][0]['status']=='PAID'
        assert db.get(OwnerPayout,payout.id).payment_reference=='BANK-PAID-REVIEW'
        assert db.get(OwnerPayout,payout.id).status=='PAID'
        report=readiness.report(db,mode='test',view='balances')
        assert report['page_totals']['actual_paid']=='84.00' and report['page_totals']['reserved_entitlement']=='0.00'


def test_future_dated_settings_api_records_settlement_actor_reason_and_retry(configured_api,monkeypatch):
    from app.services import gym_financial_settings
    from test_financial_agreements import NOW
    monkeypatch.setattr(gym_financial_settings,'utcnow',lambda:NOW)
    client,headers,engine=configured_api
    raw=gym_financial_settings.defaults();raw['settlements']=settlement()
    body={'mode':'test','gym_id':1,'expected_version':0,'expected_effective_version_id':None,
        'effective_from':(NOW+timedelta(days=1)).isoformat(),'settings':raw,'reason':'Explicit future settlement schedule',
        'acknowledge_configuration_only':True}
    path='/api/v1/admin/financial-settings'
    first=client.post(path,json=body,headers={**headers[5],'Idempotency-Key':'settlement-version-one'})
    assert first.status_code==200,first.text
    row=first.json();assert row['actor_id']==5 and row['reason']==body['reason']
    assert row['terms']['financial_settings']['settlements']['holding_days']==2
    assert client.post(path,json=body,headers={**headers[5],'Idempotency-Key':'settlement-version-one'}).json()['id']==row['id']
    assert client.get(path+'?mode=test&gym_id=1',headers=headers[5]).json()['effective'] is None
    body={**body,'expected_version':1,'effective_from':(NOW+timedelta(days=2)).isoformat(),'settings':{**raw,'settlements':{**settlement(),'holding_days':5}}}
    second=client.post(path,json=body,headers={**headers[5],'Idempotency-Key':'settlement-version-two'})
    assert second.status_code==200,second.text
    with Session(engine) as db:
        assert db.get(FinancialAgreementVersion,row['id']).terms['financial_settings']['settlements']['holding_days']==2
        assert db.get(FinancialAgreementVersion,second.json()['id']).terms['financial_settings']['settlements']['holding_days']==5


def test_monthly_payout_uses_admission_pinned_settlement_and_net(database,monkeypatch):
    from test_increment2_mysql import configure
    from test_gym_visit_payout_mysql import setup
    from app.services.gym_financial_settings import defaults
    from app.services import gym_visit_payouts as visits
    from app.core.config import settings
    from app.models.auth import Role,UserRole
    from app.schemas.owner_payout import PayoutCreate
    engine,now=database
    monkeypatch.setattr(settings,'source_evidence_enabled',True)
    monkeypatch.setattr(settings,'marketplace_allocations_enabled',True)
    monkeypatch.setattr(settings,'marketplace_payouts_enabled',True)
    monkeypatch.setattr(visits,'utcnow',lambda:now+timedelta(days=60))
    monkeypatch.setattr(owner_payouts,'utcnow',lambda:now+timedelta(days=60))
    raw=defaults();raw['settlements']=settlement()
    with Session(engine) as db:
        configure(db,now,settings=raw)
        role=Role(name='ADMIN');db.add(role);db.flush();db.add(UserRole(user_id=3,role_id=role.id));db.commit()
    events=setup(engine,now,wallet_only=True)
    with Session(engine) as db:
        rows=[visits.allocate_visit(db,identifier) for identifier in events];db.commit()
        visits.finalize_month(db,mode='test',gym_id=1,period=now.date().replace(day=1));db.commit()
        pos=owner_payouts.financial_position(db,rows[0],now=now+timedelta(days=60))
        assert pos['entitlement']==30 and pos['status']=='AVAILABLE'
        body=PayoutCreate(items=[{'visit_payout_id':rows[0].id,'amount':'30'}],reason='Explicit monthly fixture reservation')
        payout=owner_payouts.create(db,3,body,'monthly-policy-request');db.commit()
        assert payout.status=='PENDING_APPROVAL' and payout.payment_reference is None
        assert owner_payouts.financial_position(db,rows[0])['remaining']==0


def test_confirmed_zero_and_nonzero_tax_are_visible_without_rewriting(prepared):
    from app.models.payment_checkout import PaymentCheckout
    from app.core.time import stored_instant
    engine,now,identifier=prepared
    with Session(engine) as db:
        sources=[]
        for amount in ('0.00','18.00'):
            checkout=PaymentCheckout(id=str(uuid4()),user_id=1,source_key=uuid4().hex,kind='SINGLE_GYM',provider='RAZORPAY',
                mode='test',key_id='fixture',amount=118,currency='INR',snapshot={'gym_id':1},status='PAID',created_at=stored_instant(now))
            db.add(checkout);db.flush()
            payload={'gym_id':1,'financial_configuration':{'status':'PINNED'},'transaction_basis':{'price_amount':'118','discount_amount':'0',
                'tax_amount':amount,'currency':'INR','price_representation':'GROSS_BEFORE_DISCOUNT','tax_status':'EVIDENCED'}}
            source=SourceEvidence(id=str(uuid4()),idempotency_key=uuid4().hex,event_type='MEMBERSHIP_PURCHASE_RECORDED',source_type='CHECKOUT',
                source_id=checkout.id,checkout_id=checkout.id,mode='test',evidence_status='VERIFIED_SOURCE',occurred_at=checkout.created_at,
                created_at=checkout.created_at,payload=payload,payload_hash=digest(payload))
            db.add(source);sources.append(source)
        db.commit()
        result=readiness.report(db,mode='test',view='sources')
        statuses={row['tax']['status'] for row in result['items']}
        assert {'CONFIRMED_ZERO','CONFIRMED_NONZERO'}<=statuses
        assert all(digest(source.payload)==source.payload_hash for source in sources)