from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.core.time import stored_instant
from app.models.access import Checkin,CustomerDailyAccess,AccessQrToken
from app.models.membership import UserMembership
from app.models.payment_checkout import PaymentCheckout,PaymentAttempt
from app.models.financial_agreement import FinancialAgreementScope,FinancialAgreementVersion
from app.models.gym_visit_payout import GymVisitPayout
from app.models.source_evidence import SourceOutbox
from app.schemas.accounting_policy import AccountingPolicy
from app.services import source_evidence
from app.services.gym_visit_payouts import allocate_visit
from app.services.marketplace_calculation import AllocationBlocked
from test_customer_policy_mysql import database
from test_marketplace_booking_mysql import gates
from test_financial_agreements import payload


def setup(engine,now,limit=2,cap='75',platform=None,wallet_only=False):
    at=stored_instant(now)
    with Session(engine) as db:
        scope=FinancialAgreementScope(mode='test',scope_key='DEFAULT');db.add(scope);db.flush()
        data=payload()['terms'];policy=AccountingPolicy().model_dump(mode='json')
        policy['selection']['MULTI_GYM_VISIT']={'instant':'CHECKIN','approval':{'status':'APPROVED','reference':'Visit decision'}}
        data['policy_contract']=policy
        data['multi_gym']={'payout_per_visit':'50','visits_per_member_month':limit,'payout_cap_per_member_month':cap}
        data['visit_payout_contract']={'approval':{'status':'APPROVED','reference':'Visit-only approval'},'period_timezone':'Asia/Kolkata',
            'platform_cap_mode':'PER_MEMBERSHIP_ALL_GYMS' if platform else 'NOT_APPLICABLE','platform_monthly_cap':platform,
            'cap_exhaustion':'ALLOW_PARTIAL_TO_CAP','cap_order':'SERIALIZED_PROCESSING_ORDER',
            'fee_readiness':'HOLD_PAYOUT_PENDING_FEE_DISTRIBUTION'}
        db.add(FinancialAgreementVersion(scope_id=scope.id,version=1,effective_from=at-timedelta(days=2),terms=data,action='AGREEMENT',
            agreement_reference='Visit fixture',reason='Independent payout policy',ca_status='PENDING',actor_id=3,
            request_key=uuid4().hex,request_hash='0'*64,created_at=at-timedelta(days=3)))
        checkout=PaymentCheckout(id=str(uuid4()),user_id=1,source_key=uuid4().hex,kind='MULTI_GYM',mode='test',provider='RAZORPAY',
            key_id='fixture',amount=0 if wallet_only else 100,currency='INR',snapshot={},status='PAID',gateway_payment_id=None if wallet_only else 'pay_'+uuid4().hex,created_at=at-timedelta(days=1))
        db.add(checkout);db.flush()
        if wallet_only:
            from app.models.wallet import WalletTransaction
            from app.models.checkout_funding import CheckoutFunding
            debit=WalletTransaction(account_id=1,user_id=1,checkout_id=checkout.id,direction='OUT',txn_type='PAYMENT',amount=100,currency='INR')
            db.add(debit);db.flush()
            db.add(CheckoutFunding(checkout_id=checkout.id,user_id=1,total_amount=100,wallet_amount=100,gateway_amount=0,
                currency='INR',mode='test',state='DEBITED',request_wallet='100',wallet_transaction_id=debit.id,expires_at=at))
        else:
            db.add(PaymentAttempt(id=str(uuid4()),checkout_id=checkout.id,external_id=checkout.gateway_payment_id,status='SUCCESS',amount=100,currency='INR',refunded_amount=0))
        member=db.get(UserMembership,1);member.gateway_checkout_id=checkout.id
        db.flush();ids=[]
        for n in range(3):
            stamp=at+timedelta(days=n)
            daily=CustomerDailyAccess(user_id=1,membership_id=1,access_type='MULTI_GYM',access_date=now.date()+timedelta(days=n),
                access_key=uuid4().hex,status='USED',used_gym_id=1)
            db.add(daily);db.flush()
            token=AccessQrToken(daily_access_id=daily.id,token_hash=uuid4().hex,valid_from=stamp-timedelta(minutes=1),expires_at=stamp+timedelta(minutes=1),status='USED')
            db.add(token);db.flush()
            scan=Checkin(user_id=1,membership_id=1,daily_access_id=daily.id,gym_id=1,qr_token_id=token.id,status='SUCCESS',checkin_time=stamp,access_source='MEMBERSHIP_ACCESS')
            db.add(scan);db.flush();daily.checkin_id=scan.id;token.checkin_id=scan.id;db.flush()
            source_evidence.attendance(db,scan,token,membership=member,daily=daily)
            # Explicit historical fixture: the old cap tests exercise evidence
            # recorded before commercial admission binding existed, not a new
            # admission with missing gym configuration.
            if not db.scalar(select(FinancialAgreementScope.id).where(FinancialAgreementScope.gym_id==1)):
                from app.models.source_evidence import SourceEvidence
                from app.services.marketplace_allocations import digest
                from sqlalchemy import update
                evidence=db.scalar(select(SourceEvidence).where(SourceEvidence.event_type=='MULTI_GYM_VISIT_VERIFIED',SourceEvidence.source_id==str(scan.id)))
                historical=dict(evidence.payload);historical.pop('financial_configuration',None)
                db.execute(update(SourceEvidence).where(SourceEvidence.id==evidence.id).values(payload=historical,payload_hash=digest(historical)))
            ids.append(db.scalar(select(SourceOutbox.id).where(SourceOutbox.event_type=='MULTI_GYM_VISIT_VERIFIED',SourceOutbox.source_id==str(scan.id))))
        db.commit();return ids


def test_fixed_visit_caps_limits_and_no_leftover_earnings(database):
    engine,now=database;ids=setup(engine,now)
    with Session(engine) as db:
        rows=[]
        for identifier in ids:
            row=allocate_visit(db,identifier);db.commit();rows.append(row)
        assert [r.approved_amount for r in rows]==[50,25,0]
        assert rows[-1].status=='VISIT_LIMIT_REACHED'
        assert all(r.snapshot['fitigo_earnings'] is None for r in rows)
        assert allocate_visit(db,ids[0]).id==rows[0].id
        assert db.scalar(select(func.sum(GymVisitPayout.approved_amount)))==75


def test_platform_cap_applies(database):
    engine,now=database;ids=setup(engine,now,limit=10,cap='500',platform='60')
    with Session(engine) as db:
        for identifier in ids:allocate_visit(db,identifier);db.commit()
        assert db.scalar(select(func.sum(GymVisitPayout.approved_amount)))==60


def test_concurrent_cap_cannot_overpay(database):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    engine,now=database;ids=setup(engine,now,limit=10,cap='50');barrier=Barrier(2)
    def run(identifier):
        with Session(engine) as db:
            barrier.wait(timeout=20);row=allocate_visit(db,identifier);db.commit();return row.approved_amount
    with ThreadPoolExecutor(max_workers=2) as pool:amounts=list(pool.map(run,ids[:2]))
    assert sum(amounts)==50


def test_rejected_checkin_never_qualifies(database):
    engine,now=database;ids=setup(engine,now)
    with Session(engine) as db:
        first=db.scalars(select(Checkin).order_by(Checkin.id)).first();first.status='REJECTED';db.commit()
        with pytest.raises(AllocationBlocked):allocate_visit(db,ids[0])
        db.rollback();assert db.scalar(select(func.count(GymVisitPayout.id)))==0


def test_wallet_only_visit_can_follow_approved_monthly_payout_cycle(database,monkeypatch):
    from app.core.config import settings
    from app.models.auth import Role,UserRole
    from app.schemas.owner_payout import PayoutCreate
    from app.services import owner_payouts
    from sqlalchemy import update
    engine,now=database;ids=setup(engine,now,wallet_only=True)
    monkeypatch.setattr(settings,'marketplace_payouts_enabled',True)
    with Session(engine) as db:
        agreement=db.scalars(select(FinancialAgreementVersion)).one()
        from copy import deepcopy
        data=deepcopy(agreement.terms)
        data['settlements']['minimum_payout']='1.00'
        data['policy_contract']['settlements']={'approval':{'status':'APPROVED','reference':'Fixture monthly approval'},
            'monthly_cutoff_day':1,'short_month':'LAST_CALENDAR_DAY','cutoff_time':'12:00:00','timezone':'Asia/Kolkata',
            'holding_days':0,'eligible_deductions':[],'partial_settlement':'FULL_ENTITLEMENT_ONLY',
            'failed_settlement':'REMAIN_OUTSTANDING_REQUIRE_EVIDENCE'}
        db.execute(update(FinancialAgreementVersion).where(FinancialAgreementVersion.id==agreement.id).values(terms=data))
        role=Role(name='ADMIN');db.add(role);db.flush();db.add(UserRole(user_id=3,role_id=role.id));db.commit();db.expire_all()
        visit=allocate_visit(db,ids[0]);db.commit()
        assert visit.fee_status=='WALLET_ONLY_NO_GATEWAY_FEE'
        body=PayoutCreate(items=[{'visit_payout_id':visit.id,'amount':'50'}],reason='Monthly verified visit payout')
        monkeypatch.setattr(owner_payouts,'utcnow',lambda:now)
        with pytest.raises(AllocationBlocked,match='cutoff'):owner_payouts.create(db,3,body,'before-cutoff')
        db.rollback()
        monkeypatch.setattr(owner_payouts,'utcnow',lambda:now+timedelta(days=35))
        payout=owner_payouts.create(db,3,body,'monthly-wallet-payout');db.commit()
        assert payout.amount==50 and payout.status=='PENDING_APPROVAL'