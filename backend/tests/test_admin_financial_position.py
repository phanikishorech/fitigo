"""Financial reconciliation on disposable MySQL; no working DB or gateway calls."""
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_owner_dashboard_mysql import mysql_api, pytestmark, DAY
from test_owner_dashboard_metrics import booking, paid_booking, checkin
from app.core.time import IST, stored_instant
from app.models.auth import Role, UserRole
from app.models.access import AccessQrToken
from app.models.booking import Payment
from app.models.payment_checkout import PaymentAttempt
from app.models.wallet import WalletAccount, WalletTransaction
from app.core.security import create_access_token
from app.services.admin_financial_service import AdminFinancialService

AT = stored_instant(datetime.combine(DAY, datetime.min.time(), tzinfo=IST) + timedelta(hours=12))


def verified(db, *, state='CONFIRMED', attend=False, mode='test', price=150, gym=1, at=AT):
    row = booking(db, gym, day=DAY, status=state)
    row.total_price = row.unit_price = price
    checkout = paid_booking(db, row, price, at=at, mode=mode)
    payment = db.scalar(select(Payment).where(Payment.booking_id == row.id))
    payment.external_ref = checkout.gateway_payment_id
    db.add(PaymentAttempt(id=str(uuid4()), checkout_id=checkout.id, external_id=checkout.gateway_payment_id,
        status='SUCCESS', amount=price, currency='INR', refunded_amount=0, first_seen_at=at))
    if attend:
        scan = checkin(db, gym, booked=row, at=at)
        token = db.get(AccessQrToken, scan.qr_token_id)
        token.valid_from = at-timedelta(hours=1); token.expires_at=at+timedelta(hours=1)
    db.flush()
    return row, checkout


def report(db, **kwargs):
    return AdminFinancialService(db).report(date_from=DAY, date_to=DAY, mode='test', **kwargs)


def test_empty_mysql_report_has_unknown_not_invented_policies(mysql_api):
    with Session(mysql_api[2]) as db:
        data = report(db)
        assert data['revenue']['attended_booking_value'] == '0.00'
        assert data['revenue']['recognized_total']['value'] is None
        assert data['settlements']['total_payable']['value'] is None
        assert data['wallet']['outstanding'] == '0.00'


def test_attended_cancelled_confirmed_no_show_and_modes_are_separate(mysql_api):
    with Session(mysql_api[2]) as db:
        verified(db)
        verified(db, attend=True)
        verified(db, state='CANCELLED')
        no_show, _ = verified(db); no_show.attendance_status='NO_SHOW'; no_show.attendance_marked_at=AT
        verified(db, attend=True, mode='live', price=999)
        db.commit()
        data=report(db)
        assert data['revenue']['attended_booking_value']=='150.00'
        assert data['revenue']['attended_booking_count']==1
        assert data['revenue']['no_show_gross']=='150.00'
        assert data['revenue']['no_show_fitigo_income']['value'] is None
        assert data['platform']['completed_visits']==1
        assert data['bookings']['cancelled']==1
        assert sum(Decimal(r['attended_value']) for r in data['series'])==150
        assert sum(Decimal(r['attended_value']) for r in data['gyms'])==150
        assert data['payments']['undated'][0]['gross_collections']=='600.00'
        assert data['payments']['dated_collections']['value'] is None
        again = report(db)
        assert again['revenue'] == data['revenue']  # Repeated reads cannot accumulate revenue.


def test_wallet_liability_uses_net_ledger_and_exposes_discrepancy(mysql_api):
    with Session(mysql_api[2]) as db:
        account=WalletAccount(user_id=3,balance=110,currency='INR',payment_mode='test');db.add(account);db.flush()
        db.add_all([WalletTransaction(account_id=account.id,user_id=3,direction='IN',txn_type='CANCELLATION_CREDIT',amount=150,currency='INR',created_at=AT),
                    WalletTransaction(account_id=account.id,user_id=3,direction='OUT',txn_type='PAYMENT',amount=40,currency='INR',created_at=AT)])
        db.commit();data=report(db)['wallet']
        assert data['outstanding']=='110.00' and data['cancellation_credits']=='150.00' and data['spending']=='40.00'
        assert Decimal(data['opening_ledger_balance'])+Decimal(data['credits'])-Decimal(data['debits'])==Decimal(data['closing_ledger_balance'])
        assert data['source_liability']['value'] is None
        account.balance=200;db.commit()
        data=report(db)['wallet'];assert data['outstanding'] is None and data['mismatched_accounts']==1


def test_admin_only_and_identical_dashboard_analytics_report(mysql_api):
    from app.routers.admin import router
    client,headers,engine=mysql_api
    client.app.include_router(router,prefix='/api/v1')
    with Session(engine) as db:
        db.add(Role(id=2,name='ADMIN'));db.flush();db.add(UserRole(user_id=5,role_id=2));verified(db,attend=True);db.commit()
    params={'date_from':str(DAY),'date_to':str(DAY),'mode':'test','financial':'true'}
    results=[]
    for path in ('dashboard/summary','analytics','reports/financial'):
        assert client.get('/api/v1/admin/'+path,params=params,headers=headers[1]).status_code==403
        response=client.get('/api/v1/admin/'+path,params=params,headers=headers[5])
        assert response.status_code==200,response.text
        data=response.json();data.pop('generated_at');results.append(data)
        assert response.headers['cache-control']=='no-store'
    assert results[0]==results[1]==results[2]


@pytest.mark.parametrize('problem', ['pending', 'failed', 'refund', 'partial', 'review', 'manual', 'wrong_gym', 'outside_window', 'amount', 'currency', 'missing_attempt'])
def test_unverified_or_invalid_attendance_cannot_earn(mysql_api, problem):
    from app.models.access import Checkin
    with Session(mysql_api[2]) as db:
        row, checkout = verified(db, attend=problem != 'manual')
        payment = db.scalar(select(Payment).where(Payment.booking_id == row.id))
        attempt = db.scalar(select(PaymentAttempt).where(PaymentAttempt.checkout_id == checkout.id))
        if problem in {'pending', 'failed'}: attempt.status = problem.upper(); checkout.status = problem.upper(); payment.status = 'INITIATED'
        if problem in {'refund', 'partial'}: attempt.refunded_amount = 150 if problem == 'refund' else 10; attempt.status='REFUNDED' if problem=='refund' else 'PARTIALLY_REFUNDED'
        if problem == 'review': checkout.status='REVIEW_REQUIRED'
        if problem == 'manual': row.attendance_status='ATTENDED'; row.attendance_marked_at=AT
        if problem == 'wrong_gym': db.scalar(select(Checkin)).gym_id=2
        if problem == 'outside_window': db.scalar(select(Checkin)).checkin_time=AT+timedelta(days=1)
        if problem == 'amount': payment.amount=1
        if problem == 'currency': attempt.currency='USD'
        if problem == 'missing_attempt': db.delete(attempt)
        db.commit()
        assert report(db)['revenue']['attended_booking_value']=='0.00'


def test_first_checkin_date_not_scheduled_or_purchase_date_and_group_once(mysql_api):
    with Session(mysql_api[2]) as db:
        row, _ = verified(db, attend=True, at=AT-timedelta(days=1))
        row.quantity=2;row.slot_date=DAY
        scan=checkin(db,1,booked=row,visitor_index=1,at=AT)
        token=db.get(AccessQrToken,scan.qr_token_id);token.valid_from=AT-timedelta(hours=1);token.expires_at=AT+timedelta(hours=1)
        db.commit()
        assert report(db)['revenue']['attended_booking_value']=='0.00'
        yesterday=AdminFinancialService(db).report(date_from=DAY-timedelta(days=1),date_to=DAY-timedelta(days=1),mode='test')
        assert yesterday['revenue']['attended_booking_value']=='150.00'
        full=AdminFinancialService(db).report(date_from=DAY-timedelta(days=1),date_to=DAY,mode='test')
        assert full['revenue']['attended_booking_value']=='150.00' and full['platform']['completed_visits']==2


def test_ist_midnight_and_no_show_mark_date(mysql_api):
    from app.core.time import ist_day_bounds
    start,end=ist_day_bounds(DAY)
    start,end=start.replace(tzinfo=None),end.replace(tzinfo=None)
    with Session(mysql_api[2]) as db:
        for at in (start-timedelta(seconds=1),start,end-timedelta(seconds=1),end):verified(db,attend=True,at=at)
        row,_=verified(db);row.attendance_status='NO_SHOW';row.attendance_marked_at=end;db.commit()
        data=report(db)
        assert data['revenue']['attended_booking_value']=='300.00'
        assert data['revenue']['no_show_gross']=='0.00'
        assert data['bookings']['no_show']==1


def test_duplicate_provider_id_is_review_not_double_collection(mysql_api):
    with Session(mysql_api[2]) as db:
        _,first=verified(db)
        _,second=verified(db)
        attempts=list(db.scalars(select(PaymentAttempt)))
        attempts[1].external_id=attempts[0].external_id
        db.commit();data=report(db)['payments']
        assert data['duplicate_transaction_ids_excluded']==1
        assert data['mismatches']==1
        assert data['undated'][0]['gross_collections']=='0.00'


@pytest.mark.parametrize('mode', ['test', 'live'])
def test_wallet_mode_and_per_account_discrepancies_never_cancel_out(mysql_api,mode):
    with Session(mysql_api[2]) as db:
        for uid,balance,credit,row_mode in ((1,100,90,mode),(2,90,100,mode),(3,999,999,'live' if mode=='test' else 'test')):
            acct=WalletAccount(user_id=uid,balance=balance,currency='INR',payment_mode=row_mode);db.add(acct);db.flush()
            db.add(WalletTransaction(account_id=acct.id,user_id=uid,direction='IN',txn_type='TOPUP',amount=credit,currency='INR',created_at=AT))
        db.commit()
        data=AdminFinancialService(db).report(date_from=DAY,date_to=DAY,mode=mode)['wallet']
        assert data['ledger_net']=='190.00' and data['reconciliation_difference']=='0.00'
        assert data['mismatched_accounts']==2 and data['outstanding'] is None


def test_ledger_filter_authorization_and_current_liability_not_date_filtered(mysql_api):
    from app.routers.admin import router
    client,headers,engine=mysql_api;client.app.include_router(router,prefix='/api/v1')
    with Session(engine) as db:
        db.add(Role(id=2,name='ADMIN'));db.flush();db.add(UserRole(user_id=5,role_id=2))
        account=WalletAccount(user_id=3,balance=150,currency='INR',payment_mode='test');db.add(account);db.flush()
        db.add(WalletTransaction(account_id=account.id,user_id=3,direction='IN',txn_type='CANCELLATION_CREDIT',amount=150,currency='INR',created_at=AT-timedelta(days=2)))
        db.commit();data=report(db)['wallet']
        assert data['outstanding']=='150.00' and data['credits']=='0.00'
    path='/api/v1/admin/reports/wallet-ledger'
    assert client.get(path,headers=headers[1]).status_code==403
    params={'date_from':str(DAY-timedelta(days=2)),'date_to':str(DAY),'mode':'test','direction':'IN','txn_type':'CANCELLATION_CREDIT'}
    response=client.get(path,params=params,headers=headers[5]);assert response.status_code==200,response.text
    assert response.json()['total']==1 and len(response.json()['items'])==1
    assert 'email' not in response.text and 'password' not in response.text
    assert client.get(path,params={**params,'offset':1},headers=headers[5]).json()['items']==[]


def test_reports_never_write_or_call_gateways(mysql_api,monkeypatch):
    from sqlalchemy import event
    from app.services import payment_providers
    def fail(*args,**kwargs):raise AssertionError('Analytics must not call payment providers')
    monkeypatch.setattr(payment_providers,'get_provider',fail)
    with Session(mysql_api[2]) as db:
        verified(db,attend=True);db.commit()
    writes=[]
    def inspect_sql(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE','REPLACE')):writes.append(statement)
    event.listen(mysql_api[2],'before_cursor_execute',inspect_sql)
    try:
        with Session(mysql_api[2]) as db:
            data=report(db);assert data['revenue']['attended_booking_value']=='150.00'
            AdminFinancialService(db).wallet_ledger(date_from=DAY,date_to=DAY,mode='test')
        assert writes==[]
    finally:event.remove(mysql_api[2],'before_cursor_execute',inspect_sql)


def test_no_show_mutation_cannot_recognize_twice(mysql_api,monkeypatch):
    from app.services.booking_service import BookingService
    from app.services import owner_booking_policy
    from app.models.gym import GymOperatingHours
    from datetime import time
    from fastapi import HTTPException
    monkeypatch.setattr(owner_booking_policy,'utcnow',lambda:datetime.combine(DAY+timedelta(days=1),time(12),tzinfo=IST))
    monkeypatch.setattr(BookingService,'_now',lambda self:AT)
    with Session(mysql_api[2]) as db:
        row,_=verified(db)
        db.add(GymOperatingHours(gym_id=1,day_of_week=DAY.weekday(),open_time=time(6),close_time=time(22),is_closed=False));db.commit()
        service=BookingService(db)
        service.owner_mark_attendance(owner_user_id=1,booking_id=row.id,attendance_status='NO_SHOW')
        assert report(db)['revenue']['no_show_gross']=='150.00'
        with pytest.raises(HTTPException):service.owner_mark_attendance(owner_user_id=1,booking_id=row.id,attendance_status='NO_SHOW')
        db.rollback()
        assert report(db)['revenue']['no_show_gross']=='150.00'


def test_source_filter_retains_pending_attempts_and_unattributable_is_null(mysql_api):
    with Session(mysql_api[2]) as db:
        row,checkout=verified(db)
        checkout.status='PENDING';row.status='PENDING_PAYMENT'
        db.scalar(select(Payment).where(Payment.booking_id==row.id)).status='INITIATED'
        db.scalar(select(PaymentAttempt)).status='PENDING';db.commit()
        data=report(db,source='RAZORPAY')
        assert data['bookings']['pending']==1
        assert data['payments']['attempts']['pending']==1
        assert data['payments']['undated'][0]['gross_collections']=='0.00'
        assert not data['wallet']['applicable'] and data['series'][0]['wallet_credits'] is None


def test_refund_evidence_keeps_gross_collection_and_reversal_separate(mysql_api):
    with Session(mysql_api[2]) as db:
        _,checkout=verified(db,attend=True)
        attempt=db.scalar(select(PaymentAttempt));attempt.status='PARTIALLY_REFUNDED';attempt.refunded_amount=40
        checkout.status='REVIEW_REQUIRED';db.commit()
        data=report(db)
        assert data['revenue']['attended_booking_value']=='0.00'
        cash=data['payments']['undated'][0]
        assert cash['gross_collections']=='150.00' and cash['refunds_recorded']=='40.00' and cash['net_recorded']=='110.00'
        assert report(db)['payments']['undated']==data['payments']['undated']


def test_new_financial_endpoint_rejects_invalid_filters(mysql_api):
    from app.routers.admin import router
    client,headers,engine=mysql_api;client.app.include_router(router,prefix='/api/v1')
    with Session(engine) as db:
        db.add(Role(id=2,name='ADMIN'));db.flush();db.add(UserRole(user_id=5,role_id=2));db.commit()
    for params in ({'mode':'mixed'},{'source':'DUMMY'},{'gym_id':0},{'date_from':str(DAY)},
                   {'date_from':str(DAY),'date_to':str(DAY-timedelta(days=1))}):
        assert client.get('/api/v1/admin/reports/financial',params=params,headers=headers[5]).status_code==422
    assert client.get('/api/v1/admin/reports/financial',params={'gym_id':999},headers=headers[5]).status_code==404