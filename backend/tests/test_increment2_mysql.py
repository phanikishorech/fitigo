from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.core.time import stored_instant
from app.models.financial_agreement import FinancialAgreementScope,FinancialAgreementVersion
from app.models.gym import Gym
from app.models.source_evidence import SourceEvidence,SourceOutbox
from app.models.payment_checkout import PaymentCheckout
from app.models.gym_visit_payout import GymVisitPayout,GymMonthlyCalculation,MembershipVisitFee
from app.services.gym_financial_settings import defaults,binding_at
from app.services.marketplace_allocations import allocate_event,digest
from app.services.marketplace_calculation import AllocationBlocked
from app.services import source_evidence,gym_visit_payouts as visits
from test_customer_policy_mysql import database
from test_marketplace_booking_mysql import gates,setup as booking_setup
from test_gym_visit_payout_mysql import setup as visit_setup


def configure(db,now,gym_id=1,settings=None,version=1,start=None):
    parent=db.scalar(select(FinancialAgreementScope).where(FinancialAgreementScope.scope_key==f'GYM:{gym_id}',FinancialAgreementScope.mode=='test'))
    if not parent:
        parent=FinancialAgreementScope(mode='test',scope_key=f'GYM:{gym_id}',gym_id=gym_id);db.add(parent);db.flush()
    row=FinancialAgreementVersion(scope_id=parent.id,version=version,effective_from=start or stored_instant(now)-timedelta(days=2),
        terms={'financial_settings':settings or defaults()},action='AGREEMENT',agreement_reference='Increment2 fixture',reason='Explicit commercial fixture',
        ca_status='PENDING',actor_id=3,request_key=uuid4().hex,request_hash='0'*64,created_at=stored_instant(now)-timedelta(days=3))
    db.add(row);db.flush();return row


def bind_purchase_fixture(db,cid,now,settings=None,gym_id=1):
    configure(db,now,gym_id,settings)
    checkout=db.get(PaymentCheckout,cid)
    source=db.scalar(select(SourceEvidence).where(SourceEvidence.checkout_id==cid,SourceEvidence.event_type=='BOOKING_PURCHASE_RECORDED'))
    # Fixture construction only: no application evidence is mutated by integration.
    from sqlalchemy import update
    payload={**source.payload,'financial_configuration':binding_at(db,'test',gym_id,checkout.created_at)}
    db.execute(update(SourceEvidence).where(SourceEvidence.id==source.id).values(payload=payload,payload_hash=digest(payload)))
    db.flush();db.expire_all()


@pytest.mark.parametrize('no_show,percent,fee_percent',[(False,80,25),(True,60,100)])
def test_configured_booking_outcome_checkout_version_and_late_fee(database,no_show,percent,fee_percent):
    engine,now=database;ids,cid=booking_setup(engine,now,no_show=no_show,fee=None)
    raw=defaults();key='no_show' if no_show else 'individual'
    raw[key]['revenue']={'gym_percent':str(percent),'fitigo_percent':str(100-percent)}
    raw[key]['gateway_fee']={'gym_percent':str(fee_percent),'fitigo_percent':str(100-fee_percent)}
    with Session(engine) as db:
        bind_purchase_fixture(db,cid,now,raw)
        later=defaults();later[key]['revenue']={'gym_percent':'10','fitigo_percent':'90'}
        configure(db,now,settings=later,version=2,start=stored_instant(now)-timedelta(minutes=5))
        db.commit()
        rows=allocate_event(db,ids[0]);db.commit()
        assert all(r.gym_gross_share==percent for r in rows)
        assert all(r.gym_owner_net_entitlement is None for r in rows)
        saved=rows[0].calculation_hash
        assert allocate_event(db,ids[0])[0].calculation_hash==saved
        checkout=db.get(PaymentCheckout,cid)
        evidence=source_evidence.snapshot(db,'PAYMENT_DETAILS_VERIFIED','PAYMENT_ATTEMPT',checkout.gateway_payment_id,
            checkout=checkout,payload={'provider_payment_id':checkout.gateway_payment_id,'verification_status':'VERIFIED',
                'verification_source':'AUTHENTICATED_PROVIDER_FETCH','fee_amount':'3.00','fee_basis':'INCLUDING_TAX'})
        db.flush();event=db.scalar(select(SourceOutbox.id).where(SourceOutbox.evidence_id==evidence.id))
        from app.services.marketplace_corrections import apply_late_fee
        correction=apply_late_fee(db,rows[0].id,event);db.commit()
        assert correction.gym_gateway_fee_share==Decimal(fee_percent)/100
        assert rows[0].calculation_hash==saved


def test_missing_checkout_configuration_does_not_use_other_gym(database):
    engine,now=database;ids,cid=booking_setup(engine,now)
    with Session(engine) as db:
        db.add(Gym(id=2,owner_user_id=3,name='Other gym',status='APPROVED'));db.flush()
        configure(db,now,gym_id=2)
        from sqlalchemy import update
        evidence=db.scalar(select(SourceEvidence).where(SourceEvidence.checkout_id==cid,SourceEvidence.event_type=='BOOKING_PURCHASE_RECORDED'))
        payload={**evidence.payload,'financial_configuration':binding_at(db,'test',1,db.get(PaymentCheckout,cid).created_at)}
        db.execute(update(SourceEvidence).where(SourceEvidence.id==evidence.id).values(payload=payload,payload_hash=digest(payload)));db.commit()
        with pytest.raises(AllocationBlocked,match='no applicable gym configuration'):allocate_event(db,ids[0])


def prepare_month(database,monkeypatch,*,wallet=False):
    engine,now=database
    # Configure before admissions so the real attendance producer captures pins.
    with Session(engine) as db: configure(db,now);db.commit()
    ids=visit_setup(engine,now,wallet_only=wallet)
    monkeypatch.setattr(visits,'utcnow',lambda:now+timedelta(days=60))
    with Session(engine) as db:
        rows=[visits.allocate_visit(db,i) for i in ids];db.commit()
        return engine,now,ids,[r.id for r in rows]


def test_monthly_completion_and_single_membership_fee_budget(database,monkeypatch):
    engine,now,events,ids=prepare_month(database,monkeypatch)
    with Session(engine) as db:
        row=db.get(GymVisitPayout,ids[0]);assert row.applied_cap is None
        assert visits.monthly_position(db,row)['gross'] is None
        month=visits.finalize_month(db,mode='test',gym_id=1,period=now.date().replace(day=1));db.commit()
        assert month.gross_amount==90 and month.snapshot['verified_visits']==3
        assert visits.finalize_month(db,mode='test',gym_id=1,period=month.period).id==month.id
        assert visits.monthly_position(db,row)['net'] is None
        with pytest.raises(AllocationBlocked) as error:visits.attribute_membership_fee(db,row.checkout_id)
        assert error.value.code=='FEE_PENDING'
        checkout=db.get(PaymentCheckout,row.checkout_id)
        source_evidence.snapshot(db,'PAYMENT_DETAILS_VERIFIED','PAYMENT_ATTEMPT',checkout.gateway_payment_id,checkout=checkout,
            payload={'provider_payment_id':checkout.gateway_payment_id,'verification_status':'VERIFIED',
                'verification_source':'AUTHENTICATED_PROVIDER_FETCH','fee_amount':'2.37','fee_basis':'INCLUDING_TAX'})
        db.flush();fee=visits.attribute_membership_fee(db,checkout.id);db.commit()
        assert sum(Decimal(v['fee_amount']) for v in fee.snapshot['visits'])==Decimal('2.37')
        assert all(Decimal(v['gym_fee'])==0 for v in fee.snapshot['visits'])
        assert visits.monthly_position(db,row)['net']==30
        assert visits.attribute_membership_fee(db,checkout.id).id==fee.id
        assert db.scalar(select(func.count(MembershipVisitFee.id)))==1
        assert visits.allocate_visit(db,events[0]).id==row.id


def test_wallet_monthly_completion_and_append_only_invalidation(database,monkeypatch):
    engine,now,events,ids=prepare_month(database,monkeypatch,wallet=True)
    with Session(engine) as db:
        month=visits.finalize_month(db,mode='test',gym_id=1,period=now.date().replace(day=1));db.commit()
        row=db.get(GymVisitPayout,ids[0]);assert visits.monthly_position(db,row)['net']==30
        from app.models.auth import Role,UserRole
        role=Role(name='ADMIN');db.add(role);db.flush();db.add(UserRole(user_id=3,role_id=role.id))
        from app.models.access import Checkin
        db.get(Checkin,row.checkin_id).status='REJECTED'
        evidence=source_evidence.invalidated_multi_gym_visit(db,row.checkin_id,3,'Verified invalid admission review')
        db.flush();revision=visits.finalize_month(db,mode='test',gym_id=1,period=month.period,correction_evidence_id=evidence.id,actor_id=3);db.commit()
        assert revision.revision==2 and revision.gross_amount==60
        assert month.gross_amount==90 and db.scalar(select(func.count(GymMonthlyCalculation.id)))==2
        assert visits.monthly_position(db,row)['status']=='INVALIDATED'
        assert visits.finalize_month(db,mode='test',gym_id=1,period=month.period,correction_evidence_id=evidence.id,actor_id=3).id==revision.id


@pytest.mark.parametrize('wallet,gateway,fee',[(0,100,'2.36'),(100,0,None),(60,40,'0.94')])
def test_single_gym_configuration_funding_and_snapshot(database,wallet,gateway,fee):
    from test_marketplace_membership_mysql import setup
    from sqlalchemy import update
    engine,now=database;event=setup(engine,now,Decimal(wallet),Decimal(gateway),Decimal(fee) if fee else None)
    raw=defaults();raw['single_gym']['revenue']={'gym_percent':'92','fitigo_percent':'8'}
    raw['single_gym']['gateway_fee']={'gym_percent':'25','fitigo_percent':'75'}
    with Session(engine) as db:
        configure(db,now,settings=raw)
        purchase=db.scalar(select(SourceEvidence).where(SourceEvidence.event_type=='MEMBERSHIP_PURCHASE_RECORDED'))
        checkout=db.get(PaymentCheckout,purchase.checkout_id)
        data={**purchase.payload,'financial_configuration':binding_at(db,'test',1,checkout.created_at)}
        db.execute(update(SourceEvidence).where(SourceEvidence.id==purchase.id).values(payload=data,payload_hash=digest(data)));db.commit()
        row=allocate_event(db,event)[0];db.commit()
        assert row.gym_gross_share==92 and row.fitigo_gross_commission==8
        assert row.wallet_amount==wallet and row.gateway_amount==gateway
        assert row.calculation_snapshot['result']['entitlement_timing']=='UPFRONT'
        assert row.calculation_snapshot['commercial_shares']['gateway_fee']['gym_percent']=='25'
        assert row.gateway_fee==Decimal(fee or 0)
        assert allocate_event(db,event)[0].id==row.id


def test_different_gyms_and_gateway_only_cart_partition(database):
    from app.models.booking import Booking
    from app.models.access import Checkin,AccessQrToken
    from app.models.checkout_funding import CheckoutFunding,BookingFunding
    from app.services.checkout_funding import reserve
    from sqlalchemy import update
    engine,now=database;events,cid=booking_setup(engine,now,fee='3.01')
    with Session(engine) as db:
        checkout=db.get(PaymentCheckout,cid);checkout.kind='CART';checkout.amount=Decimal(600)
        from app.models.payment_checkout import PaymentAttempt
        db.scalar(select(PaymentAttempt).where(PaymentAttempt.checkout_id==cid)).amount=Decimal(600)
        db.add(Gym(id=2,owner_user_id=3,name='Gym B',status='APPROVED'));db.flush()
        booking=Booking(user_id=1,gym_id=2,gym_slot_id=1,slot_date=now.date(),quantity=1,unit_price=300,total_price=300,
            currency='INR',status='CONFIRMED',checkout_id=cid,expires_at=stored_instant(now)+timedelta(days=1),visitor_names=['B'])
        db.add(booking);db.flush()
        raw=defaults();raw['individual']['revenue']={'gym_percent':'80','fitigo_percent':'20'}
        raw['individual']['gateway_fee']={'gym_percent':'100','fitigo_percent':'0'}
        configure(db,now,gym_id=2,settings=raw)
        bind_purchase_fixture(db,cid,now)
        reserve(db,checkout,None);db.flush()
        assert checkout.amount==600 and db.get(CheckoutFunding,cid).wallet_amount==0
        assert db.scalar(select(func.sum(BookingFunding.gateway_amount)).where(BookingFunding.checkout_id==cid))==600
        source_evidence.snapshot(db,'BOOKING_PURCHASE_RECORDED','BOOKING_CHECKOUT',f'{cid}:{booking.id}',checkout=checkout,
            occurred_at=checkout.created_at,gym_id=2,observe_owner=True,payload={'booking_id':booking.id,
            'financial_configuration':binding_at(db,'test',2,checkout.created_at),
            'transaction_basis':{'price_amount':'330','discount_amount':'30','tax_amount':'18',
                'currency':'INR','price_representation':'GROSS_BEFORE_DISCOUNT'}})
        stamp=stored_instant(now)
        token=AccessQrToken(booking_id=booking.id,visitor_index=0,token_hash=uuid4().hex,
            valid_from=stamp-timedelta(minutes=1),expires_at=stamp+timedelta(minutes=1),status='USED')
        db.add(token);db.flush()
        scan=Checkin(user_id=1,gym_id=2,booking_id=booking.id,qr_token_id=token.id,visitor_index=0,status='SUCCESS',
            checkin_time=stamp,access_source='BOOKING_ACCESS')
        db.add(scan);db.flush();source_evidence.attendance(db,scan,token,booking=booking)
        event=db.scalar(select(SourceOutbox.id).where(SourceOutbox.event_type=='BOOKING_VISITOR_ATTENDED',SourceOutbox.source_id==str(scan.id)))
        # The reused group fixture admits indices 0 and 2; admit its remaining
        # purchased place to assert conservation across the complete cart.
        original=db.get(Booking,1)
        extra=AccessQrToken(booking_id=1,visitor_index=1,token_hash=uuid4().hex,valid_from=stamp-timedelta(minutes=1),expires_at=stamp+timedelta(minutes=1),status='USED')
        db.add(extra);db.flush()
        admission=Checkin(user_id=1,gym_id=1,booking_id=1,qr_token_id=extra.id,visitor_index=1,status='SUCCESS',checkin_time=stamp,access_source='BOOKING_ACCESS')
        db.add(admission);db.flush();source_evidence.attendance(db,admission,extra,booking=original)
        events.append(db.scalar(select(SourceOutbox.id).where(SourceOutbox.event_type=='BOOKING_VISITOR_ATTENDED',SourceOutbox.source_id==str(admission.id))))
        db.commit()
        a=[allocate_event(db,e)[0] for e in events];b=allocate_event(db,event)[0];db.commit()
        assert sum(r.gym_gross_share for r in a)==255
        assert b.gym_gross_share==Decimal('225.60') and b.eligible_amount==282
        assert sum(r.gateway_fee for r in a)+b.gateway_fee==Decimal('3.01')
        assert b.gym_gateway_fee_share==b.gateway_fee==Decimal('1.50')
        assert all(r.agreement_version_id!=b.agreement_version_id for r in a)


def test_concurrent_configured_allocation_and_month_completion(database,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    engine,now,events,ids=prepare_month(database,monkeypatch,wallet=True)
    barrier=Barrier(2)
    def finish(_):
        with Session(engine) as db:
            barrier.wait(timeout=20)
            result=visits.finalize_month(db,mode='test',gym_id=1,period=now.date().replace(day=1));db.commit();return result.id
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(finish,range(2)))
    assert results[0]==results[1]
    with Session(engine) as db:assert db.scalar(select(func.count(GymMonthlyCalculation.id)))==1


def test_month_not_complete_and_missing_admission_block(database,monkeypatch):
    engine,now,events,ids=prepare_month(database,monkeypatch,wallet=True)
    monkeypatch.setattr(visits,'utcnow',lambda:now)
    with Session(engine) as db:
        with pytest.raises(AllocationBlocked) as error:visits.finalize_month(db,mode='test',gym_id=1,period=now.date().replace(day=1))
        assert error.value.code=='MONTH_NOT_COMPLETE'
    monkeypatch.setattr(visits,'utcnow',lambda:now+timedelta(days=60))
    with Session(engine) as db:
        from app.models.access import Checkin
        db.get(Checkin,db.get(GymVisitPayout,ids[0]).checkin_id).status='REJECTED';db.commit()
        with pytest.raises(AllocationBlocked) as error:visits.finalize_month(db,mode='test',gym_id=1,period=now.date().replace(day=1))
        assert error.value.code=='MONTH_INCOMPLETE'


@pytest.mark.parametrize('count,expected',[(50,1500),(100,3000),(160,4800),(200,6000)])
def test_monthly_volume_end_to_end_without_caps(database,monkeypatch,count,expected):
    from app.models.access import Checkin,CustomerDailyAccess,AccessQrToken
    from app.models.membership import UserMembership
    engine,now,events,identifiers=prepare_month(database,monkeypatch,wallet=True)
    with Session(engine) as db:
        member=db.get(UserMembership,1)
        # Multiple users/memberships, never multiple admissions for one daily access.
        from app.models.auth import User
        original=db.get(PaymentCheckout,member.gateway_checkout_id)
        stamp=stored_instant(now)
        for index in range(count-3):
            user=User(email=f'volume-{index}@example.test',password_hash='unused',status='ACTIVE');db.add(user);db.flush()
            checkout=PaymentCheckout(id=str(uuid4()),user_id=user.id,source_key=uuid4().hex,kind='MULTI_GYM',provider='RAZORPAY',
                mode='test',key_id='fixture',amount=Decimal(100),currency='INR',snapshot={},status='PAID',gateway_payment_id='pay_'+uuid4().hex,created_at=stamp-timedelta(days=1))
            db.add(checkout);db.flush()
            from app.models.payment_checkout import PaymentAttempt
            db.add(PaymentAttempt(id=str(uuid4()),checkout_id=checkout.id,external_id=checkout.gateway_payment_id,status='SUCCESS',amount=100,currency='INR',refunded_amount=0))
            membership=UserMembership(user_id=user.id,membership_type='MULTI_GYM',gateway_checkout_id=checkout.id,status='ACTIVE',payment_status='PAID',
                start_at=stamp-timedelta(days=1),end_at=stamp+timedelta(days=20),paid_amount=100,currency='INR',payment_provider='RAZORPAY')
            db.add(membership);db.flush()
            daily=CustomerDailyAccess(user_id=user.id,membership_id=membership.id,access_type='MULTI_GYM',access_date=now.date(),access_key=uuid4().hex,status='USED',used_gym_id=1)
            db.add(daily);db.flush()
            token=AccessQrToken(daily_access_id=daily.id,token_hash=uuid4().hex,valid_from=stamp-timedelta(minutes=1),expires_at=stamp+timedelta(minutes=1),status='USED')
            db.add(token);db.flush()
            scan=Checkin(user_id=user.id,membership_id=membership.id,daily_access_id=daily.id,gym_id=1,qr_token_id=token.id,status='SUCCESS',checkin_time=stamp,access_source='MEMBERSHIP_ACCESS')
            db.add(scan);db.flush();daily.checkin_id=scan.id;token.checkin_id=scan.id
            source_evidence.attendance(db,scan,token,membership=membership,daily=daily)
            event=db.scalar(select(SourceOutbox.id).where(SourceOutbox.event_type=='MULTI_GYM_VISIT_VERIFIED',SourceOutbox.source_id==str(scan.id)))
            visits.allocate_visit(db,event)
        db.commit()
        month=visits.finalize_month(db,mode='test',gym_id=1,period=now.date().replace(day=1));db.commit()
        assert month.gross_amount==expected and month.snapshot['verified_visits']==count
        assert sum(Decimal(v['gross_amount']) for v in month.snapshot['visits'])==expected
        assert month.snapshot['fitigo_earnings'] is None


def test_admission_version_changes_and_independent_multi_gym_fee_percentages(database,monkeypatch):
    engine,now=database
    with Session(engine) as db:
        first=configure(db,now)
        changed=defaults();changed['multi_gym']['reference_amount']='4000.00'
        changed['multi_gym']['gateway_fee']={'gym_percent':'100','fitigo_percent':'0'}
        second=configure(db,now,settings=changed,version=2,start=stored_instant(now)+timedelta(hours=1))
        first_id,second_id=first.id,second.id;db.commit()
    events=visit_setup(engine,now)
    monkeypatch.setattr(visits,'utcnow',lambda:now+timedelta(days=60))
    with Session(engine) as db:
        rows=[visits.allocate_visit(db,event) for event in events];db.commit()
        assert [r.agreement_version_id for r in rows]==[first_id,second_id,second_id]
        month=visits.finalize_month(db,mode='test',gym_id=1,period=now.date().replace(day=1));db.commit()
        assert month.gross_amount==110
        checkout=db.get(PaymentCheckout,rows[0].checkout_id)
        source_evidence.snapshot(db,'PAYMENT_DETAILS_VERIFIED','PAYMENT_ATTEMPT',checkout.gateway_payment_id,checkout=checkout,
            payload={'provider_payment_id':checkout.gateway_payment_id,'verification_status':'VERIFIED',
                'verification_source':'AUTHENTICATED_PROVIDER_FETCH','fee_amount':'3.00','fee_basis':'INCLUDING_TAX'})
        db.flush();fee=visits.attribute_membership_fee(db,checkout.id);db.commit()
        assert [Decimal(item['gym_fee']) for item in fee.snapshot['visits']]==[0,1,1]
        assert [visits.monthly_position(db,row)['net'] for row in rows]==[30,39,39]


def test_correction_blocks_reserved_month_and_preserves_snapshot(database,monkeypatch):
    from app.models.owner_payout import OwnerPayout,OwnerPayoutItem
    from app.models.auth import Role,UserRole
    from app.models.access import Checkin
    engine,now,events,ids=prepare_month(database,monkeypatch,wallet=True)
    with Session(engine) as db:
        month=visits.finalize_month(db,mode='test',gym_id=1,period=now.date().replace(day=1));db.commit()
        row=db.get(GymVisitPayout,ids[0]);fingerprint=month.snapshot_hash
        role=Role(name='ADMIN');db.add(role);db.flush();db.add(UserRole(user_id=3,role_id=role.id))
        payout=OwnerPayout(id=str(uuid4()),mode='test',gym_id=1,owner_user_id=3,category='MULTI_GYM',
            period_start=month.period,period_end=now.date(),entitlement_amount=30,deduction_amount=0,amount=30,currency='INR',
            status='APPROVED',version=1,requested_by=3,request_key=uuid4().hex,request_hash='0'*64,deductions=[],created_at=stored_instant(now))
        db.add(payout);db.flush();db.add(OwnerPayoutItem(id=str(uuid4()),payout_id=payout.id,visit_payout_id=row.id,amount=30))
        db.get(Checkin,row.checkin_id).status='REJECTED';db.flush()
        evidence=source_evidence.invalidated_multi_gym_visit(db,row.checkin_id,3,'Source rejection reviewed')
        db.commit()
        with pytest.raises(AllocationBlocked) as error:visits.finalize_month(db,mode='test',gym_id=1,period=month.period,correction_evidence_id=evidence.id,actor_id=3)
        assert error.value.code=='PAYOUT_RESERVATION_REVIEW'
        assert month.snapshot_hash==fingerprint and db.scalar(select(func.count(GymMonthlyCalculation.id)))==1


def test_configured_booking_cancellation_preserves_original(database):
    from app.models.booking import Booking
    from app.services.marketplace_corrections import reverse_cancelled
    engine,now=database;events,cid=booking_setup(engine,now)
    with Session(engine) as db:
        bind_purchase_fixture(db,cid,now);db.commit()
        original=allocate_event(db,events[0])[0];db.commit();old_hash=original.calculation_hash
        booking=db.get(Booking,1);booking.status='CANCELLED';booking.cancelled_at=stored_instant(now)+timedelta(hours=1)
        source_evidence.operational_cancellation(db,booking,3);db.flush()
        event=db.scalar(select(SourceOutbox.id).where(SourceOutbox.event_type=='BOOKING_CANCELLED'))
        reversal=reverse_cancelled(db,original.id,event);db.commit()
        assert reversal.gym_gross_share==-original.gym_gross_share
        assert reversal.gym_gateway_fee_share==-original.gym_gateway_fee_share
        assert original.calculation_hash==old_hash
        assert reverse_cancelled(db,original.id,event).id==reversal.id


def test_multi_gym_months_are_isolated_by_gym_and_report_unknown_net(database,monkeypatch):
    from app.models.access import Checkin,CustomerDailyAccess,AccessQrToken
    from app.models.membership import UserMembership
    from app.services.marketplace_reporting import report
    engine,now,events,ids=prepare_month(database,monkeypatch)
    with Session(engine) as db:
        db.add(Gym(id=2,owner_user_id=3,name='Different volume terms',status='APPROVED',multi_gym_enabled=True));db.flush()
        raw=defaults();raw['multi_gym']['reference_amount']='6000.00'
        configure(db,now,gym_id=2,settings=raw)
        member=db.get(UserMembership,1);stamp=stored_instant(now)+timedelta(days=3)
        daily=CustomerDailyAccess(user_id=1,membership_id=1,access_type='MULTI_GYM',access_date=(now+timedelta(days=3)).date(),access_key=uuid4().hex,status='USED',used_gym_id=2)
        db.add(daily);db.flush()
        token=AccessQrToken(daily_access_id=daily.id,token_hash=uuid4().hex,valid_from=stamp-timedelta(minutes=1),expires_at=stamp+timedelta(minutes=1),status='USED')
        db.add(token);db.flush()
        scan=Checkin(user_id=1,gym_id=2,membership_id=1,daily_access_id=daily.id,qr_token_id=token.id,status='SUCCESS',checkin_time=stamp,access_source='MEMBERSHIP_ACCESS')
        db.add(scan);db.flush();daily.checkin_id=scan.id;token.checkin_id=scan.id
        source_evidence.attendance(db,scan,token,membership=member,daily=daily)
        event=db.scalar(select(SourceOutbox.id).where(SourceOutbox.event_type=='MULTI_GYM_VISIT_VERIFIED',SourceOutbox.source_id==str(scan.id)))
        visits.allocate_visit(db,event);db.commit()
        first=visits.finalize_month(db,mode='test',gym_id=1,period=now.date().replace(day=1))
        second=visits.finalize_month(db,mode='test',gym_id=2,period=now.date().replace(day=1));db.commit()
        assert first.gross_amount==90 and second.gross_amount==60
        data=report(db,mode='test',date_from=now.date().replace(day=1),date_to=now.date().replace(day=28),gym_id=2,category='MULTI_GYM')
        assert data['totals']['multi_gym_visit_payout']=='60.00'
        assert data['totals']['multi_gym_fitigo_earnings'] is None
        assert data['totals']['total_owner_payable'] is None
        assert data['monthly_visits'][0]['visits']==1