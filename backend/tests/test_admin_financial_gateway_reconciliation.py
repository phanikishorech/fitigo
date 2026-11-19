"""Real isolated MySQL purchase flows, mocked gateways, read-only reporting."""
from datetime import timedelta, timezone
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_split_payment import api, razorpay_api, cashfree_api, booking_api, source, create, verify, balance
from app.models.wallet import WalletAccount, WalletTransaction
from app.models.booking import Booking
from app.models.access import AccessQrToken, Checkin
from app.models.membership import UserMembership
from app.services.admin_financial_service import AdminFinancialService
from app.core.time import IST, stored_instant
from test_booking_access_qr import NOW
import pytest


def test_split_purchase_wallet_liability_and_attendance_reconcile(api):
    balance(api,40)
    with Session(api[2]) as db:
        acct=db.scalar(select(WalletAccount).where(WalletAccount.user_id==1))
        db.add(WalletTransaction(account_id=acct.id,user_id=1,direction='IN',txn_type='TOPUP',amount=40,currency='INR'));db.commit()
    record=create(api,source(api)).json()
    entity=api[3].pay(record)
    assert verify(api,record,entity).json()['status']=='PAID'
    assert verify(api,record,entity).json()['status']=='PAID'
    with Session(api[2]) as db:
        service=AdminFinancialService(db)
        params=dict(date_from=NOW.date(),date_to=NOW.date(),mode='test')
        before=service.report(**params)
        assert before['revenue']['attended_booking_value']=='0.00'
        assert before['wallet']['outstanding']=='0.00'
        row=db.get(Booking,record['booking_ids'][0]);token=db.scalar(select(AccessQrToken).where(AccessQrToken.booking_id==row.id))
        db.add(Checkin(user_id=1,gym_id=row.gym_id,qr_token_id=token.id,booking_id=row.id,visitor_index=0,
            access_source='BOOKING_ACCESS',checkin_time=stored_instant(NOW),status='SUCCESS'))
        db.commit();data=service.report(**params)
        assert data['revenue']['attended_booking_value']=='150.00'
        assert data['revenue']['attended_wallet_funded_value']=='40.00'
        assert data['platform']['completed_visits']==1
        assert sum(Decimal(row['gross_collections']) for row in data['payments']['undated'])==110
        assert data['settlements']['attended_payable']['value'] is None
        assert service.report(**params,source='WALLET')['revenue']['attended_booking_value']=='150.00'


def test_cancelled_paid_split_booking_is_liability_not_revenue(api,monkeypatch):
    from app.services import booking_cancellation
    monkeypatch.setattr(booking_cancellation,'utcnow',lambda:NOW.replace(hour=7))
    balance(api,40)
    with Session(api[2]) as db:
        acct=db.scalar(select(WalletAccount).where(WalletAccount.user_id==1))
        db.add(WalletTransaction(account_id=acct.id,user_id=1,direction='IN',txn_type='TOPUP',amount=40,currency='INR'));db.commit()
    record=create(api,source(api)).json();assert verify(api,record,api[3].pay(record)).json()['status']=='PAID'
    path=f"/api/v1/bookings/{record['booking_ids'][0]}/cancel"
    assert api[0].post(path,headers=api[1][1],json={}).status_code==200
    assert api[0].post(path,headers=api[1][1],json={}).status_code==409
    with Session(api[2]) as db:
        data=AdminFinancialService(db).report(date_from=NOW.date(),date_to=NOW.date(),mode='test')
        assert data['wallet']['outstanding']=='150.00'
        assert data['revenue']['attended_booking_value']=='0.00'
        assert data['bookings']['cancelled']==1
        assert sum(Decimal(r['gross_collections']) for r in data['payments']['undated'])==110


@pytest.mark.parametrize('kind', ['SINGLE_GYM', 'MULTI_GYM'])
def test_membership_sale_gym_attribution_not_each_visit(api, kind):
    from test_cashfree_payments import source_for
    balance(api,0)
    if kind == 'MULTI_GYM': payload=source_for(api,kind)
    else:
        quote=api[0].get('/api/v1/memberships/gyms/1/plans/1/wallet-quote',headers=api[1][1]).json()
        payload={'kind':kind,'gym_id':1,'plan_id':1,'accepted_quote':quote['quote_token']}
    record=create(api,payload).json();entity=api[3].pay(record)
    assert verify(api,record,entity).json()['status']=='PAID'
    assert verify(api,record,entity).json()['status']=='PAID'
    with Session(api[2]) as db:
        membership=db.scalar(select(UserMembership))
        day=membership.created_at.replace(tzinfo=timezone.utc).astimezone(IST).date()
        service=AdminFinancialService(db);data=service.report(date_from=day,date_to=day,mode='test')
        expected = '1000.00' if kind=='MULTI_GYM' else '500.00'
        assert data['memberships']['categories'][kind]['sales_count']==1
        assert data['memberships']['categories'][kind]['sales_value']==expected
        assert data['memberships']['categories'][kind]['recognized_revenue']['value'] is None
        # Two valid membership visits must not create another membership sale.
        from app.models.access import CustomerDailyAccess
        from datetime import datetime, time
        for index in range(2):
            instant=stored_instant(datetime.combine(day,time(10+index),tzinfo=IST))
            daily=CustomerDailyAccess(user_id=1,membership_id=membership.id,access_type=kind,
                access_date=day+timedelta(days=index),access_key=f'financial-member-{index}',
                gym_id=1 if kind=='SINGLE_GYM' else None,status='USED',used_gym_id=1)
            db.add(daily);db.flush()
            token=AccessQrToken(daily_access_id=daily.id,token_hash=f'financial-member-{index}',
                valid_from=instant-timedelta(hours=1),expires_at=instant+timedelta(hours=1))
            db.add(token);db.flush()
            db.add(Checkin(user_id=1,gym_id=1,daily_access_id=daily.id,membership_id=membership.id,
                qr_token_id=token.id,access_source='MEMBERSHIP_ACCESS',status='SUCCESS',checkin_time=instant))
        db.commit()
        repeated=service.report(date_from=day,date_to=day,mode='test')
        assert repeated['memberships']['categories'][kind]['sales_value']==expected
        assert repeated['platform']['completed_visits']==2
        assert repeated['revenue']['attended_booking_value']=='0.00'
        for gid in (1,2):
            scoped=service.report(date_from=day,date_to=day,mode='test',gym_id=gid)
            assert scoped['memberships']['categories'][kind]['sales_value']==(expected if kind=='SINGLE_GYM' and gid==1 else '0.00')
            assert scoped['payments']['applicable'] is False