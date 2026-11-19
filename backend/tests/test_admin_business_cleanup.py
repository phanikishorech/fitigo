from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import select,event,func
from sqlalchemy.orm import Session
from app.models.source_evidence import SourceEvidence
from app.models.auth import Role,UserRole
from app.models.access import Checkin,AccessQrToken,CustomerDailyAccess
from app.models.membership import UserMembership,MembershipPause
from app.models.payment_checkout import PaymentCheckout,PaymentAttempt
from app.services.marketplace_allocations import digest
from app.services.admin_business import summary,memberships
from test_admin_financial_position import verified,AT,DAY
from test_owner_dashboard_mysql import mysql_api,pytestmark


def evidence(db,checkout,at=AT):
    data={'provider_payment_id':checkout.gateway_payment_id,'verification_status':'VERIFIED','verification_source':'AUTHENTICATED_PROVIDER_FETCH'}
    db.add(SourceEvidence(id=str(uuid4()),idempotency_key=uuid4().hex,event_type='PAYMENT_CAPTURED',source_type='PAYMENT_ATTEMPT',
        source_id=checkout.gateway_payment_id,checkout_id=checkout.id,mode=checkout.mode,evidence_status='VERIFIED_SOURCE',occurred_at=at,created_at=at,
        amount=checkout.amount,currency='INR',payload=data,payload_hash=digest(data)))


def report(db):return summary(db,date_from=DAY,date_to=DAY,mode='test')


def test_unknown_capture_dates_are_not_sales_dates(mysql_api):
    with Session(mysql_api[2]) as db:
        verified(db,attend=True);db.commit()
        data=report(db)
        assert data['overall']['visits']==1
        assert data['collections']['total'] is None
        assert data['collections']['undated_purchases']==1
        assert data['collections']['fitigo_commission'] is None


def test_partial_collections_expose_verified_categories_and_exact_exclusions(mysql_api):
    with Session(mysql_api[2]) as db:
        _, dated = verified(db, price=150); evidence(db, dated)
        _, undated = verified(db, price=250)
        db.commit()
        data = report(db)['collections']
        assert data['total'] is None and data['complete'] is False
        assert data['known_dated_categories'] == {'individual': '150.00', 'single_gym': '0.00', 'multi_gym': '0.00'}
        assert data['known_dated_total'] == '150.00'
        assert data['exclusions'] == [{'checkout_id': undated.id, 'category': 'individual', 'reason': 'PAYMENT_DATE_MISSING'}]
        assert data['exclusion_reasons'] == {'PAYMENT_DATE_MISSING': 1}


def test_collection_completeness_is_independent_by_category(mysql_api):
    with Session(mysql_api[2]) as db:
        _, dated = verified(db, price=300); evidence(db, dated)
        verified(db, price=150)
        db.commit()
        data = report(db)['collections']
        assert data['category_complete'] == {'individual': False, 'single_gym': True, 'multi_gym': True}
        assert data['excluded_by_category'] == {'individual': 1, 'single_gym': 0, 'multi_gym': 0}
        assert data['categories'] == {'individual': None, 'single_gym': '0.00', 'multi_gym': '0.00'}
        assert data['known_dated_categories']['individual'] == '300.00'
        assert data['total'] is None
        assert data['sharing_availability']['gym_gross_share']['reason'] == 'NO_RECORDED_ALLOCATIONS'
        assert data['sharing_availability']['fitigo_commission']['reason'] == 'NO_RECORDED_ALLOCATIONS'


@pytest.mark.parametrize('net', ['12.50', None])
def test_sharing_displays_only_existing_report_values_without_deriving_from_collections(mysql_api, monkeypatch, net):
    from app.services import marketplace_reporting
    def recorded(db, **filters):
        assert filters == {'mode': 'test', 'date_from': DAY, 'date_to': DAY, 'gym_id': None}
        return {'available': True, 'total': 1, 'visit_total': 1,
            'totals': {'gym_gross_share': '85.00', 'multi_gym_visit_payout': '30.00', 'fitigo_net_commission': net}}
    monkeypatch.setattr(marketplace_reporting, 'report', recorded)
    with Session(mysql_api[2]) as db:
        data = report(db)['collections']
        assert data['gym_gross_share'] == '115.00'
        assert data['fitigo_commission'] == net
        assert data['sharing_availability']['gym_gross_share']['status'] == 'RECORDED_SUBTOTAL'
        assert data['sharing_availability']['fitigo_commission']['status'] == ('UNAVAILABLE' if net is None else 'RECORDED_SUBTOTAL')


@pytest.mark.parametrize('problem', ['status', 'amount', 'currency', 'hash', 'conflict'])
def test_capture_evidence_must_match_verified_payment(mysql_api, problem):
    with Session(mysql_api[2]) as db:
        _, checkout = verified(db); evidence(db, checkout)
        source = next(row for row in db.new if isinstance(row, SourceEvidence))
        if problem == 'status': source.evidence_status = 'SOURCE_DATA_MISSING'
        if problem == 'amount': source.amount = 1
        if problem == 'currency': source.currency = 'USD'
        if problem == 'hash': source.payload_hash = '0' * 64
        if problem == 'conflict': evidence(db, checkout, AT + timedelta(hours=1))
        db.commit()
        data = report(db)['collections']
        assert data['total'] is None
        assert data['known_dated_total'] == '0.00'
        assert data['exclusion_reasons'] == {('PAYMENT_DATE_CONFLICT' if problem == 'conflict' else 'PAYMENT_EVIDENCE_INVALID'): 1}


def test_wallet_unavailable_scope_explains_why_and_all_gyms_reconciles(mysql_api):
    from app.models.wallet import WalletAccount, WalletTransaction
    with Session(mysql_api[2]) as db:
        account = WalletAccount(user_id=3, balance=110, currency='INR', payment_mode='test')
        db.add(account); db.flush()
        for direction, kind, value in [('IN', 'TOPUP', 100), ('IN', 'CANCELLATION_CREDIT', 50), ('OUT', 'PAYMENT', 60), ('IN', 'REVERSAL', 20)]:
            db.add(WalletTransaction(account_id=account.id, user_id=3, direction=direction, txn_type=kind, amount=value, currency='INR', created_at=AT))
        db.commit()
        scoped = summary(db, date_from=DAY, date_to=DAY, mode='test', gym_id=1)['wallet']
        assert scoped['outstanding'] is None and 'platform-wide' in scoped['reason']
        assert report(db)['wallet']['outstanding'] == '110.00'
        assert summary(db, date_from=DAY, date_to=DAY, mode='live')['wallet']['outstanding'] == '0.00'
        account.balance = 120; db.commit()
        broken = report(db)['wallet']
        assert broken['outstanding'] is None
        assert broken['review_accounts'] == [{'account_id': account.id, 'user_id': 3, 'stored_balance': '120.00', 'ledger_net': '110.00', 'invalid_records': 0}]
        assert '1 wallet account' in broken['reason']


def test_later_verified_payment_date_can_complete_initial_undated_evidence(mysql_api):
    with Session(mysql_api[2]) as db:
        _, checkout = verified(db); evidence(db, checkout, None)
        initial = next(row for row in db.new if isinstance(row, SourceEvidence))
        initial.evidence_status = 'EVENT_TIME_UNAVAILABLE'
        initial.created_at = AT  # Observation time is not the missing capture date.
        db.flush()
        evidence(db, checkout)
        detail = next(row for row in db.new if isinstance(row, SourceEvidence))
        detail.event_type = 'PAYMENT_DETAILS_VERIFIED'
        db.commit()
        data = report(db)['collections']
        assert data['total'] == '150.00' and data['complete']
        assert data['exclusions'] == []


def test_collections_count_once_by_payment_date_and_visit_dedup(mysql_api):
    with Session(mysql_api[2]) as db:
        booking,checkout=verified(db,attend=True);evidence(db,checkout)
        scan=db.scalar(select(Checkin).where(Checkin.booking_id==booking.id))
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError),db.begin_nested():
            db.add(Checkin(user_id=scan.user_id,gym_id=scan.gym_id,booking_id=scan.booking_id,qr_token_id=scan.qr_token_id,
                visitor_index=scan.visitor_index,checkin_time=scan.checkin_time,status='SUCCESS',access_source='BOOKING_ACCESS'))
            db.flush()
        db.add(Checkin(user_id=scan.user_id,gym_id=scan.gym_id,booking_id=scan.booking_id,qr_token_id=scan.qr_token_id,
            visitor_index=None,checkin_time=scan.checkin_time,status='REJECTED',access_source='BOOKING_ACCESS'))
        _,other=verified(db,mode='live',price=999);evidence(db,other)
        db.commit();data=report(db)
        assert data['visits']['individual']==1 and data['overall']['visits']==1
        assert data['collections']['categories']['individual']=='150.00'
        assert data['collections']['total']=='150.00'
        assert sum(Decimal(r['individual_collections']) for r in data['series'])==150
        assert summary(db,date_from=DAY+timedelta(days=1),date_to=DAY+timedelta(days=1),mode='test')['collections']['total']=='0.00'


@pytest.mark.parametrize('kind',['SINGLE_GYM','MULTI_GYM'])
def test_membership_collection_not_repeated_for_included_visit(mysql_api,kind):
    with Session(mysql_api[2]) as db:
        checkout=PaymentCheckout(id=str(uuid4()),user_id=3,source_key=uuid4().hex,kind=kind,mode='test',provider='RAZORPAY',key_id='fixture',amount=500,currency='INR',snapshot={'gym_id':1},status='PAID',gateway_payment_id='pay_'+uuid4().hex,created_at=AT)
        db.add(checkout);db.flush();db.add(PaymentAttempt(id=str(uuid4()),checkout_id=checkout.id,external_id=checkout.gateway_payment_id,status='SUCCESS',amount=500,currency='INR',refunded_amount=0));evidence(db,checkout)
        member=UserMembership(user_id=3,gym_id=1 if kind=='SINGLE_GYM' else None,membership_type=kind,status='ACTIVE',payment_status='PAID',payment_provider='RAZORPAY',paid_amount=500,currency='INR',start_at=AT-timedelta(days=1),end_at=AT+timedelta(days=30),gateway_checkout_id=checkout.id,created_at=AT)
        db.add(member);db.flush();daily=CustomerDailyAccess(user_id=3,membership_id=member.id,access_type=kind,access_date=DAY,access_key=uuid4().hex,status='USED',used_gym_id=1)
        db.add(daily);db.flush();token=AccessQrToken(daily_access_id=daily.id,token_hash=uuid4().hex,valid_from=AT-timedelta(minutes=1),expires_at=AT+timedelta(minutes=1),status='USED');db.add(token);db.flush()
        scan=Checkin(user_id=3,gym_id=1,membership_id=member.id,daily_access_id=daily.id,qr_token_id=token.id,status='SUCCESS',checkin_time=AT,access_source='MEMBERSHIP_ACCESS');db.add(scan);db.flush();daily.checkin_id=scan.id;token.checkin_id=scan.id;db.commit()
        data=report(db)
        assert data['visits'][kind.lower()]==1
        assert data['collections']['categories'][kind.lower()]=='500.00'
        assert data['collections']['total']=='500.00'
        assert data['collections']['fitigo_commission'] is None
        assert memberships(db,kind=kind)['items'][0]['id']==member.id


def test_business_endpoints_admin_only_and_read_only(mysql_api):
    from app.routers.admin_business import router
    client,headers,engine=mysql_api;client.app.include_router(router,prefix='/api/v1/admin')
    with Session(engine) as db:
        db.add(Role(id=2,name='ADMIN'));db.flush();db.add(UserRole(user_id=5,role_id=2));booking,_=verified(db,attend=True);bid=booking.id;db.commit()
    writes=[]
    def spy(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')):writes.append(statement)
    event.listen(engine,'before_cursor_execute',spy)
    try:
        for path in (f'/business/summary?date_from={DAY}&date_to={DAY}&mode=test','/business/memberships','/business/customers/3',f'/business/bookings/{bid}/attendance'):
            assert client.get('/api/v1/admin'+path).status_code==401
            assert client.get('/api/v1/admin'+path,headers=headers[1]).status_code==403
            response=client.get('/api/v1/admin'+path,headers=headers[5]);assert response.status_code==200,response.text
            assert response.headers['cache-control']=='no-store'
        assert writes==[]
    finally:event.remove(engine,'before_cursor_execute',spy)


def test_no_show_requires_explicit_mark_and_cancellation_rate(mysql_api):
    with Session(mysql_api[2]) as db:
        verified(db) # no scan is not a no-show
        marked,_=verified(db);marked.attendance_status='NO_SHOW';marked.attendance_marked_at=AT
        incomplete,_=verified(db);incomplete.attendance_status='NO_SHOW';incomplete.attendance_marked_at=None
        verified(db,state='CANCELLED');db.commit()
        data=report(db)
        assert data['visits']['no_shows']==1 and data['bookings']['cancelled']==1
        assert data['bookings']['cancellation_rate']==25


def test_membership_states_search_and_pagination(mysql_api):
    with Session(mysql_api[2]) as db:
        from app.services import admin_business
        now=admin_business.utcnow().replace(tzinfo=None)
        for status,start,end in [('ACTIVE',now-timedelta(days=1),now+timedelta(days=20)),('ACTIVE',now-timedelta(days=40),now-timedelta(days=1)),('CANCELLED',now-timedelta(days=1),now+timedelta(days=20))]:
            db.add(UserMembership(user_id=3,gym_id=1,membership_type='SINGLE_GYM',status=status,payment_status='PAID',payment_provider='WALLET',paid_amount=100,currency='INR',start_at=start,end_at=end))
        db.flush()
        active=db.scalar(select(UserMembership).where(UserMembership.end_at>now,UserMembership.status=='ACTIVE'))
        db.add(MembershipPause(membership_id=active.id,request_key=uuid4().hex,start_date=admin_business.ist_today(),end_date=admin_business.ist_today(),days=1,previous_end_at=active.end_at,new_end_at=active.end_at+timedelta(days=1)));db.commit()
        assert memberships(db,status='PAUSED')['total']==1
        assert memberships(db,status='EXPIRED')['total']==1
        assert memberships(db,status='CANCELLED')['total']==1
        assert memberships(db,q='no-such-customer')['total']==0
        assert memberships(db,limit=1,offset=1)['total']==3
        assert len(memberships(db,limit=1,offset=1)['items'])==1


def test_wallet_metrics_use_ledger_not_booking_totals(mysql_api):
    from app.models.wallet import WalletAccount,WalletTransaction
    with Session(mysql_api[2]) as db:
        account=WalletAccount(user_id=3,balance=110,currency='INR',payment_mode='test');db.add(account);db.flush()
        db.add_all([WalletTransaction(account_id=account.id,user_id=3,direction='IN',txn_type='CANCELLATION_CREDIT',amount=150,currency='INR',created_at=AT),
            WalletTransaction(account_id=account.id,user_id=3,direction='OUT',txn_type='PAYMENT',amount=40,currency='INR',created_at=AT)])
        verified(db,price=999);db.commit()
        data=report(db)
        assert data['wallet']['outstanding']=='110.00' and data['wallet']['cancellation_credits']=='150.00'
        assert data['wallet']['spending']=='40.00'


@pytest.mark.parametrize('wallet,gateway',[(150,0),(60,90)])
def test_purchase_consideration_preserves_wallet_gateway_split(mysql_api,wallet,gateway):
    from app.models.wallet import WalletAccount,WalletTransaction
    from app.models.checkout_funding import CheckoutFunding,BookingFunding
    with Session(mysql_api[2]) as db:
        booking,checkout=verified(db,attend=True)
        attempt=db.scalar(select(PaymentAttempt).where(PaymentAttempt.checkout_id==checkout.id))
        checkout.amount=Decimal(gateway);attempt.amount=Decimal(gateway)
        if not gateway:
            from app.models.booking import Payment
            payment=db.scalar(select(Payment).where(Payment.booking_id==booking.id))
            payment.provider='WALLET';payment.external_ref=None
        account=WalletAccount(user_id=3,balance=0,currency='INR',payment_mode='test');db.add(account);db.flush()
        db.add(WalletTransaction(account_id=account.id,user_id=3,direction='IN',txn_type='TOPUP',amount=wallet,currency='INR',created_at=AT))
        debit=WalletTransaction(account_id=account.id,user_id=3,direction='OUT',txn_type='PAYMENT',amount=wallet,currency='INR',checkout_id=checkout.id,created_at=AT);db.add(debit);db.flush()
        db.add(CheckoutFunding(checkout_id=checkout.id,user_id=3,total_amount=150,wallet_amount=wallet,gateway_amount=gateway,mode='test',currency='INR',state='DEBITED',request_wallet=str(wallet),wallet_transaction_id=debit.id,expires_at=AT+timedelta(hours=1),resolved_at=AT))
        db.flush()
        db.add(BookingFunding(booking_id=booking.id,checkout_id=checkout.id,total_amount=150,wallet_amount=wallet,gateway_amount=gateway))
        if gateway:evidence(db,checkout)
        db.commit();data=report(db)
        assert data['collections']['total']=='150.00'
        assert data['collections']['categories']['individual']=='150.00'
        assert data['wallet']['spending']==f'{wallet}.00'


def test_wallet_purchase_subtotal_uses_payment_day_gym_mode_and_separate_cancellation_credit(mysql_api):
    from app.models.booking import Payment
    from app.models.wallet import WalletAccount, WalletTransaction
    from app.models.checkout_funding import CheckoutFunding, BookingFunding
    from app.models.customer_policy import BookingCancellation
    with Session(mysql_api[2]) as db:
        account = WalletAccount(user_id=3, balance=150, currency='INR', payment_mode='test')
        db.add(account); db.flush()
        db.add(WalletTransaction(account_id=account.id, user_id=3, direction='IN', txn_type='TOPUP', amount=300, currency='INR', created_at=AT))
        for index in range(2):
            booking, checkout = verified(db, price=150)
            booking.slot_date = DAY + timedelta(days=1)
            attempt = db.scalar(select(PaymentAttempt).where(PaymentAttempt.checkout_id == checkout.id))
            db.delete(attempt)
            checkout.amount = 0; checkout.gateway_payment_id = None
            payment = db.scalar(select(Payment).where(Payment.booking_id == booking.id))
            payment.provider = 'WALLET'; payment.external_ref = None
            at = AT + timedelta(minutes=index * 10)
            debit = WalletTransaction(account_id=account.id, user_id=3, direction='OUT', txn_type='PAYMENT', amount=150, currency='INR', checkout_id=checkout.id, created_at=at)
            db.add(debit); db.flush()
            funding = CheckoutFunding(checkout_id=checkout.id, user_id=3, total_amount=150, wallet_amount=150,
                gateway_amount=0, mode='test', currency='INR', state='DEBITED', request_wallet='150',
                wallet_transaction_id=debit.id, expires_at=at + timedelta(hours=1), resolved_at=at)
            db.add(funding); db.flush()
            db.add(BookingFunding(booking_id=booking.id, checkout_id=checkout.id, total_amount=150, wallet_amount=150, gateway_amount=0))
            if index == 0:
                booking.status = 'CANCELLED'; booking.cancelled_at = at + timedelta(minutes=1)
                credit = WalletTransaction(account_id=account.id, user_id=3, direction='IN', txn_type='CANCELLATION_CREDIT', amount=150, currency='INR', created_at=booking.cancelled_at)
                db.add(credit); db.flush()
                db.add(BookingCancellation(booking_id=booking.id, payment_id=payment.id, wallet_transaction_id=credit.id,
                    actor_id=3, amount=150, currency='INR', scheduled_start=at + timedelta(days=1),
                    deadline=at + timedelta(hours=21), created_at=booking.cancelled_at))
        # An undated provider purchase must not be dated by its wallet/checkout observation.
        verified(db, price=50)
        db.commit()
        data = report(db)
        assert data['collections']['known_dated_total'] == '300.00'
        assert data['collections']['known_dated_categories'] == {'individual': '300.00', 'single_gym': '0.00', 'multi_gym': '0.00'}
        assert data['collections']['total'] is None
        assert data['wallet']['cancellation_credits'] == '150.00'
        assert data['wallet']['outstanding'] == '150.00'
        assert 'Cancellation wallet credits are reported separately' in data['definitions']['collections']
        assert summary(db, date_from=DAY, date_to=DAY, mode='test', gym_id=1)['collections']['known_dated_total'] == '300.00'
        for params in ({'date_from': DAY + timedelta(days=1), 'date_to': DAY + timedelta(days=1), 'mode': 'test'},
                       {'date_from': DAY, 'date_to': DAY, 'mode': 'test', 'gym_id': 2},
                       {'date_from': DAY, 'date_to': DAY, 'mode': 'live'}):
            assert summary(db, **params)['collections']['known_dated_total'] == '0.00'
        funding.resolved_at = None; db.commit()
        assert report(db)['collections']['known_dated_total'] == '150.00'  # Never infer from ledger/booking creation.