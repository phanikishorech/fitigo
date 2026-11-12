"""Admin financial scope and cancellation semantics in isolated SQLite only."""
from datetime import timedelta
from decimal import Decimal
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.booking import Booking, Payment
from app.models.payment_checkout import PaymentCheckout
from app.models.wallet import WalletTransaction, WalletAccount
from app.services.booking_service import BookingService
from app.services.admin_booking_ops_service import AdminBookingOpsService
from test_dashboard_date_ranges import api, owner_api, get, booking, paid_booking, DAY


@pytest.mark.parametrize('mode', ['test', 'live'])
@pytest.mark.parametrize('provider', ['RAZORPAY', 'CASHFREE'])
def test_admin_dashboard_daily_and_selected_gyms_share_verified_mode_scope(api, monkeypatch, mode, provider):
    monkeypatch.setattr(settings, 'payment_env', 'sandbox' if mode == 'test' else 'production')
    with Session(api[2]) as db:
        for gym, amount, row_mode in [(1, 100, mode), (2, 200, mode), (1, 900, 'live' if mode == 'test' else 'test')]:
            row = booking(db, gym)
            checkout = paid_booking(db, row, amount, mode=row_mode)
            checkout.provider = provider
            db.flush(); db.scalar(select(Payment).where(Payment.booking_id == row.id)).provider = provider
        # Legacy PAID, wallet and wrong currency cannot become live revenue.
        for source in ['DUMMY', 'WALLET', 'RAZORPAY', 'CASHFREE']:
            row = booking(db, 1); db.add(Payment(booking_id=row.id, provider=source, status='PAID', amount=999))
        for problem in ['refund', 'partial', 'review', 'currency', 'payment_currency', 'booking_currency', 'user', 'provider', 'transaction', 'failed', 'kind']:
            row = booking(db, 1); checkout = paid_booking(db, row, 999, mode=mode)
            db.flush(); payment = db.scalar(select(Payment).where(Payment.booking_id == row.id))
            if problem == 'refund': checkout.status = payment.status = 'REFUNDED'
            if problem == 'partial': checkout.status = 'REVIEW_REQUIRED'; payment.status = 'PARTIALLY_REFUNDED'
            if problem == 'review': checkout.status = 'REVIEW_REQUIRED'
            if problem == 'currency': checkout.currency = 'USD'
            if problem == 'payment_currency': payment.currency = 'USD'
            if problem == 'booking_currency': row.currency = 'USD'
            if problem == 'user': checkout.user_id = 4
            if problem == 'provider': payment.provider = 'CASHFREE'
            if problem == 'transaction': checkout.gateway_payment_id = None
            if problem == 'failed': payment.status = 'FAILED'
            if problem == 'kind': checkout.kind = 'WALLET_TOPUP'
        db.commit()
    params = {'date_from': str(DAY), 'date_to': str(DAY)}
    summary = get(api, 'admin/dashboard/summary', params, actor=6)
    all_rows = get(api, 'admin/reports/bookings/daily', params, actor=6)
    assert Decimal(summary['revenue']['in_period']) == 300
    assert summary['revenue']['mode'] == mode
    assert summary['revenue']['date_basis'] == 'SCHEDULED_BOOKING_DATE'
    assert Decimal(all_rows[0]['paid_amount_total']) == 300 and all_rows[0]['mode'] == mode
    assert all_rows[0]['total_bookings'] == summary['bookings']['in_period'] == 18
    amounts = [Decimal(get(api, 'admin/reports/bookings/daily', {**params, 'gym_id': gym}, actor=6)[0]['paid_amount_total']) for gym in [1, 2]]
    assert amounts == [100, 200] and sum(amounts) == 300


def test_shared_cart_allocations_count_once_and_keep_documented_cancellation_basis(api):
    with Session(api[2]) as db:
        first = booking(db, 1, quantity=3, status='CANCELLED')
        checkout = paid_booking(db, first, 300)
        checkout.kind, checkout.amount = 'CART', 500
        second = booking(db, 2)
        second.checkout_id, second.attendance_status = checkout.id, 'NO_SHOW'
        db.add(Payment(booking_id=second.id, provider='RAZORPAY', amount=200, status='PAID'))
        db.commit()
    params = {'date_from': str(DAY), 'date_to': str(DAY)}
    summary = get(api, 'admin/dashboard/summary', params, actor=6)
    assert Decimal(summary['revenue']['in_period']) == 500
    assert 'remain included while paid' in summary['revenue']['basis']
    assert Decimal(get(api, 'admin/reports/bookings/daily', params, actor=6)[0]['paid_amount_total']) == 500


def test_last_30_days_excludes_future_and_thirtieth_previous_day(api):
    with Session(api[2]) as db:
        for offset, amount in [(-30, 900), (-29, 100), (0, 200), (1, 800)]:
            paid_booking(db, booking(db, 1, day=DAY+timedelta(days=offset)), amount)
        db.commit()
    assert Decimal(get(api, 'admin/dashboard/summary', {}, actor=6)['revenue']['last_30d']) == 300


@pytest.mark.parametrize('actor', ['customer', 'owner', 'admin'])
@pytest.mark.parametrize('provider', ['WALLET', 'DUMMY', 'RAZORPAY', 'CASHFREE'])
def test_cancellation_preserves_paid_state_and_never_credits_wallet(api, actor, provider):
    from app.routers.bookings import router
    api[0].app.include_router(router, prefix='/api/v1')
    with Session(api[2]) as db:
        row = booking(db, 1)
        bid = row.id
        db.add(Payment(booking_id=bid, provider=provider, status='PAID', amount=100))
        db.add(WalletAccount(user_id=3, balance=321, currency='INR'))
        db.commit()
        if actor == 'customer':
            response = api[0].post(f'/api/v1/bookings/{bid}/cancel', headers=api[1][3], json={})
            assert response.status_code == 200 and response.json()['refund_initiated'] is False
            assert 'does not initiate' in response.json()['cancellation_message']
            BookingService(db).cancel_booking(user_id=3, booking_id=bid)
        elif actor == 'owner':
            response = api[0].post(f'/api/v1/gym-owner/bookings/{bid}/cancel', headers=api[1][1], json={})
            assert response.status_code == 200 and response.json()['refund_initiated'] is False
        else:
            response = api[0].post(f'/api/v1/admin/bookings/{bid}/cancel', headers=api[1][6], json={})
            assert response.status_code == 200 and response.json()['refund_initiated'] is False
        db.expire_all()
        assert db.get(Booking, bid).status == 'CANCELLED'
        assert db.scalar(select(Payment.status).where(Payment.booking_id == bid)) == 'PAID'
        assert db.scalar(select(WalletAccount.balance).where(WalletAccount.user_id == 3)) == 321
        assert db.scalar(select(func.count(WalletTransaction.id))) == 0


def test_cancellation_retains_previously_recorded_refund(api):
    with Session(api[2]) as db:
        row = booking(db, 1)
        db.add(Payment(booking_id=row.id, provider='RAZORPAY', status='REFUNDED', amount=100)); db.commit()
        AdminBookingOpsService(db).cancel_booking(booking_id=row.id)
        assert db.scalar(select(Payment.status).where(Payment.booking_id == row.id)) == 'REFUNDED'


@pytest.mark.parametrize('provider', ['WALLET', 'DUMMY', 'RAZORPAY', 'CASHFREE'])
def test_admin_status_edit_cannot_invent_a_refund(api, provider):
    with Session(api[2]) as db:
        row = booking(db, 1); bid = row.id
        db.add(Payment(booking_id=bid, provider=provider, status='PAID', amount=100)); db.commit()
    response = api[0].post(f'/api/v1/admin/bookings/{bid}/payment/status', headers=api[1][6], json={'status': 'REFUNDED'})
    assert response.status_code == 409
    with Session(api[2]) as db:
        assert db.scalar(select(Payment.status).where(Payment.booking_id == bid)) == 'PAID'