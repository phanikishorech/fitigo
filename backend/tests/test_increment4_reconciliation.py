"""Repeatable cross-gym, cross-calendar-month fee and entitlement scenario."""
from datetime import datetime,timedelta,date
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.core.time import IST,stored_instant
from app.models.gym import Gym
from app.models.membership import UserMembership
from app.models.payment_checkout import PaymentCheckout,PaymentAttempt
from app.models.financial_agreement import FinancialAgreementScope
from app.models.access import Checkin,CustomerDailyAccess,AccessQrToken
from app.models.source_evidence import SourceOutbox
from app.services.gym_financial_settings import defaults
from app.services import source_evidence,gym_visit_payouts as visits
from app.services.financial_readiness import report
from test_customer_policy_mysql import database
from test_marketplace_booking_mysql import gates
from test_increment2_mysql import configure


def test_membership_spans_two_gyms_two_ist_months_fee_is_once(database,monkeypatch):
    engine,now=database
    stamps=[datetime(2026,11,30,23,59,tzinfo=IST),datetime(2026,12,1,0,1,tzinfo=IST),
        datetime(2026,12,2,12,tzinfo=IST),datetime(2026,12,3,12,tzinfo=IST)]
    monkeypatch.setattr(visits,'utcnow',lambda:datetime(2027,2,1,tzinfo=IST))
    with Session(engine) as db:
        db.add(FinancialAgreementScope(mode='test',scope_key='DEFAULT'));db.add(Gym(id=2,owner_user_id=3,name='Second gym',status='APPROVED',multi_gym_enabled=True));db.flush()
        configure(db,now)
        second=defaults();second['multi_gym']['reference_amount']='4500.00';second['multi_gym']['gateway_fee']={'gym_percent':'50','fitigo_percent':'50'}
        configure(db,now,gym_id=2,settings=second)
        checkout=PaymentCheckout(id=str(uuid4()),user_id=1,source_key=uuid4().hex,kind='MULTI_GYM',provider='RAZORPAY',mode='test',key_id='fixture',
            amount=1000,currency='INR',snapshot={},status='PAID',gateway_payment_id='pay_'+uuid4().hex,created_at=stored_instant(now))
        db.add(checkout);db.flush();db.add(PaymentAttempt(id=str(uuid4()),checkout_id=checkout.id,external_id=checkout.gateway_payment_id,
            amount=1000,currency='INR',status='SUCCESS',refunded_amount=0))
        member=db.get(UserMembership,1);member.gateway_checkout_id=checkout.id;member.end_at=stored_instant(datetime(2027,1,1,tzinfo=IST));member.paid_amount=1000
        db.flush();events=[]
        for stamp,gym_id in zip(stamps,[1,2,1,2]):
            at=stored_instant(stamp)
            daily=CustomerDailyAccess(user_id=1,membership_id=1,access_type='MULTI_GYM',access_date=stamp.date(),access_key=uuid4().hex,status='USED',used_gym_id=gym_id)
            db.add(daily);db.flush();token=AccessQrToken(daily_access_id=daily.id,token_hash=uuid4().hex,valid_from=at-timedelta(seconds=30),expires_at=at+timedelta(seconds=30),status='USED')
            db.add(token);db.flush();scan=Checkin(user_id=1,gym_id=gym_id,membership_id=1,daily_access_id=daily.id,qr_token_id=token.id,status='SUCCESS',checkin_time=at,access_source='MEMBERSHIP_ACCESS')
            db.add(scan);db.flush();daily.checkin_id=scan.id;token.checkin_id=scan.id;source_evidence.attendance(db,scan,token,membership=member,daily=daily)
            events.append(db.scalar(select(SourceOutbox.id).where(SourceOutbox.source_id==str(scan.id),SourceOutbox.event_type=='MULTI_GYM_VISIT_VERIFIED')))
        db.commit()
        rows=[visits.allocate_visit(db,key) for key in events];db.commit()
        assert visits.allocate_visit(db,events[0]).id==rows[0].id
        a=visits.finalize_month(db,mode='test',gym_id=1,period=date(2026,11,1))
        b=visits.finalize_month(db,mode='test',gym_id=1,period=date(2026,12,1))
        c=visits.finalize_month(db,mode='test',gym_id=2,period=date(2026,12,1));db.commit()
        assert [a.gross_amount,b.gross_amount,c.gross_amount]==[30,30,90]
        assert all(visits.monthly_position(db,row)['net'] is None for row in rows)
        source_evidence.snapshot(db,'PAYMENT_DETAILS_VERIFIED','PAYMENT_ATTEMPT',checkout.gateway_payment_id,checkout=checkout,
            payload={'provider_payment_id':checkout.gateway_payment_id,'verification_status':'VERIFIED','verification_source':'AUTHENTICATED_PROVIDER_FETCH',
                'fee_amount':'2.37','fee_basis':'INCLUDING_TAX','fee_tax_amount':'0.37'})
        db.flush();budget=visits.attribute_membership_fee(db,checkout.id);db.commit()
        assert sum(Decimal(v['fee_amount']) for v in budget.snapshot['visits'])==Decimal('2.37')
        assert [Decimal(v['fee_amount']) for v in budget.snapshot['visits']]==[Decimal('.60'),Decimal('.59'),Decimal('.59'),Decimal('.59')]
        assert sum(visits.monthly_position(db,row)['net'] for row in rows)==Decimal('149.42')
        assert visits.attribute_membership_fee(db,checkout.id).id==budget.id
        data=report(db,mode='test',view='collections')
        assert data['items'][0]['unallocated_collection']=='1000.00' and data['items'][0]['fitigo_earnings'] is None