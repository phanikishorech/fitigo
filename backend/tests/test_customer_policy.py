"""Policy boundary and financial/access regression tests on disposable SQLite."""
from datetime import datetime, timedelta, time
from decimal import Decimal
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from test_booking_access_qr import api, NOW
from app.core.time import IST, stored_instant
from app.models.auth import User
from app.models.booking import Booking, Payment
from app.models.slot import GymSlot
from app.models.wallet import WalletAccount, WalletTransaction
from app.models.membership import UserMembership, MembershipPause
from app.models.platform_membership import PlatformMembershipPlan
from app.models.customer_policy import BookingCancellation, MembershipTransfer
from app.models.access import AccessQrToken, CustomerDailyAccess, Checkin
from app.models.gym import Gym
from app.models.payment_checkout import PaymentCheckout, PaymentAttempt
from app.services import booking_cancellation as cancellation, membership_transfer as transfer, access_service
from app.services.membership_service import MembershipService
from app.services.access_service import AccessService
from app.services.membership_pause_service import MembershipPauseService
from app.routers.memberships import router as memberships_router


@pytest.fixture
def policy_api(api, monkeypatch):
    api[0].app.include_router(memberships_router, prefix='/api/v1')
    now = [datetime(2026, 10, 10, 15, tzinfo=IST)]
    monkeypatch.setattr(cancellation, 'utcnow', lambda: now[0])
    monkeypatch.setattr(transfer, 'utcnow', lambda: now[0])
    monkeypatch.setattr(access_service, 'utcnow', lambda: now[0])
    monkeypatch.setattr(access_service, 'access_today', lambda: now[0].date())
    from app.services import membership_pause_service
    monkeypatch.setattr(membership_pause_service, 'utcnow', lambda: now[0])
    return (*api, now)


def paid_booking(fixture, *, amount=Decimal('100'), provider='WALLET', status='CONFIRMED', payment_status='PAID'):
    with Session(fixture[2]) as db:
        slot = GymSlot(gym_id=1, name='Policy fixture', start_time=time(18), end_time=time(19), capacity=10, price=amount, is_active=1)
        db.add(slot); db.flush()
        booking = Booking(user_id=1, gym_id=1, gym_slot_id=slot.id, slot_date=NOW.date(), quantity=1,
            unit_price=amount, total_price=amount, currency='INR', status=status, visitor_names=['Visitor'],
            access_source='BOOKING_ACCESS', expires_at=stored_instant(NOW + timedelta(hours=10)))
        db.add(booking); db.flush()
        debit = WalletTransaction(account_id=1, user_id=1, direction='OUT', txn_type='PAYMENT', amount=amount, currency='INR')
        db.add(debit); db.flush()
        payment = Payment(booking_id=booking.id, provider=provider, status=payment_status, amount=amount, currency='INR', external_ref=f'WALLET_TXN:{debit.id}')
        db.add(payment); db.commit()
        return booking.id


def cancel_request(fixture, bid, actor=1):
    return fixture[0].post(f'/api/v1/bookings/{bid}/cancel', headers=fixture[1][actor], json={'reason': 'Plans changed'})


@pytest.mark.parametrize('delta,ok', [(0, True), (-1, True), (60, False), (10801, False)])
def test_three_hour_boundary_uses_scheduled_ist_not_creation(policy_api, delta, ok):
    bid = paid_booking(policy_api)
    policy_api[3][0] += timedelta(seconds=delta)
    result = cancel_request(policy_api, bid)
    assert result.status_code == (200 if ok else 409), result.text
    with Session(policy_api[2]) as db:
        assert db.get(Booking, bid).status == ('CANCELLED' if ok else 'CONFIRMED')
        assert db.scalar(select(func.count(BookingCancellation.id))) == int(ok)
        assert db.get(WalletAccount, 1).balance == Decimal('10100') if ok else db.get(WalletAccount, 1).balance == Decimal('10000')
        if ok:
            assert result.json()['cancellation']['wallet_credit_amount'] == '100.00'
            assert result.json()['cancellation']['deadline'].endswith('+05:30')
            assert db.get(Payment, 1).status == 'PAID'


def test_duplicate_attended_and_wrong_owner_do_not_credit(policy_api):
    bid = paid_booking(policy_api)
    assert cancel_request(policy_api, bid, actor=4).status_code == 404
    with Session(policy_api[2]) as db: db.get(Booking, bid).attendance_status = 'ATTENDED'; db.commit()
    assert cancel_request(policy_api, bid).status_code == 409
    with Session(policy_api[2]) as db: db.get(Booking, bid).attendance_status = None; db.commit()
    assert cancel_request(policy_api, bid).status_code == 200
    assert cancel_request(policy_api, bid).status_code == 409
    with Session(policy_api[2]) as db:
        assert db.scalar(select(func.count(WalletTransaction.id)).where(WalletTransaction.direction == 'IN')) == 1


@pytest.mark.parametrize('status,payment', [('PENDING_PAYMENT', 'INITIATED'), ('CONFIRMED', 'FAILED'), ('EXPIRED', 'PAID'), ('CANCELLED', 'PAID')])
def test_ineligible_states_never_credit(policy_api, status, payment):
    bid = paid_booking(policy_api, status=status, payment_status=payment)
    assert cancel_request(policy_api, bid).status_code == 409
    with Session(policy_api[2]) as db: assert db.scalar(select(func.count(BookingCancellation.id))) == 0


def test_zero_value_cancel_has_no_wallet_credit(policy_api):
    bid = paid_booking(policy_api, amount=Decimal(0), provider='FREE')
    assert cancel_request(policy_api, bid).status_code == 200
    with Session(policy_api[2]) as db:
        audit = db.scalar(select(BookingCancellation))
        assert audit.amount == 0 and audit.wallet_transaction_id is None


def test_wallet_failure_rolls_back_status_and_credit(policy_api, monkeypatch):
    bid = paid_booking(policy_api)
    from app.services.booking_access_service import BookingAccessService
    monkeypatch.setattr(BookingAccessService, 'revoke', lambda *args: (_ for _ in ()).throw(RuntimeError('Synthetic failure')))
    with pytest.raises(RuntimeError): cancel_request(policy_api, bid)
    with Session(policy_api[2]) as db:
        assert db.get(Booking, bid).status == 'CONFIRMED'
        assert db.get(WalletAccount, 1).balance == 10000
        assert db.scalar(select(func.count(BookingCancellation.id))) == 0
        assert db.scalar(select(func.count(WalletTransaction.id)).where(WalletTransaction.direction == 'IN')) == 0


@pytest.mark.parametrize('provider', ['RAZORPAY', 'CASHFREE'])
def test_gateway_credit_uses_booking_allocation_not_cart_total(policy_api, provider):
    bid = paid_booking(policy_api, provider=provider)
    with Session(policy_api[2]) as db:
        checkout = PaymentCheckout(id='policy-checkout', user_id=1, source_key='policy', kind='CART', provider=provider,
            mode='test', key_id='test', amount=300, currency='INR', snapshot={}, status='PAID', gateway_order_id='test-order', gateway_payment_id='test-payment')
        db.add(checkout); db.flush()
        db.add(PaymentAttempt(id='policy-attempt', checkout_id=checkout.id, external_id='test-payment', status='SUCCESS', amount=300, currency='INR', refunded_amount=0))
        db.get(Booking, bid).checkout_id = checkout.id
        db.get(Payment, 1).external_ref = 'test-payment'
        other = Booking(user_id=1, gym_id=1, gym_slot_id=db.get(Booking, bid).gym_slot_id, slot_date=NOW.date(), quantity=2,
            unit_price=100, total_price=200, currency='INR', status='CONFIRMED', checkout_id=checkout.id,
            expires_at=stored_instant(NOW + timedelta(hours=10)))
        db.add(other); db.flush()
        db.add(Payment(booking_id=other.id, provider=provider, status='PAID', amount=200, currency='INR', external_ref='test-payment'))
        db.commit()
    assert cancel_request(policy_api, bid).status_code == 200
    with Session(policy_api[2]) as db:
        assert db.get(WalletAccount, 1).balance == 10100
        assert db.get(PaymentCheckout, 'policy-checkout').status == 'PAID'


def test_ambiguous_split_and_test_money_never_become_live_credit(policy_api):
    bid = paid_booking(policy_api)
    with Session(policy_api[2]) as db: db.get(Payment, 1).amount = 50; db.commit()
    assert cancel_request(policy_api, bid).status_code == 409
    with Session(policy_api[2]) as db:
        db.get(Payment, 1).amount = 100; db.get(Payment, 1).provider = 'DUMMY'; db.commit()
    assert cancel_request(policy_api, bid).status_code == 409


def membership(fixture, kind='MULTI_GYM'):
    now = stored_instant(fixture[3][0])
    with Session(fixture[2]) as db:
        for uid in [1, 4]: db.get(User, uid).is_email_verified = True
        db.get(User, 4).first_name = 'Recipient'
        db.get(Gym, 1).multi_gym_enabled = True
        plan = PlatformMembershipPlan(code='policy', name='Policy plan', duration_value=30, duration_unit='DAYS', base_price=100, currency='INR', is_active=True, pause_allowed=True, max_pause_days=5)
        db.add(plan); db.flush()
        m = UserMembership(user_id=1, gym_id=None if kind == 'MULTI_GYM' else 1, membership_type=kind,
            platform_plan_id=plan.id if kind == 'MULTI_GYM' else None, status='ACTIVE', start_at=now-timedelta(days=5),
            end_at=now+timedelta(days=25), original_end_at=now+timedelta(days=24), paid_amount=100,
            currency='INR', payment_provider='WALLET', payment_status='PAID', checkout_key='original-purchase', terms_snapshot={'name': 'Original terms'})
        db.add(m); db.flush()
        db.add(MembershipPause(membership_id=m.id, request_key='past-pause', start_date=NOW.date()-timedelta(days=3),
            end_date=NOW.date()-timedelta(days=3), days=1, previous_end_at=m.original_end_at, new_end_at=m.end_at))
        db.commit(); return m.id


def preview(fixture, mid, email='qr-4@example.test'):
    # Service accepts exact verified email; HTTP EmailStr intentionally rejects .test domains.
    with Session(fixture[2]) as db: return transfer.preview(db, mid, 1, email)


def execute(fixture, mid, value, key='transfer-test-key'):
    return fixture[0].post(f'/api/v1/memberships/me/{mid}/transfer', headers={**fixture[1][1], 'Idempotency-Key': key},
        json={'confirmation_token': value['confirmation_token'], 'confirmed': True})


def test_transfer_preserves_identity_dates_pause_and_invalidates_old_qr(policy_api):
    mid = membership(policy_api)
    with Session(policy_api[2]) as db:
        old = AccessService(db).get_today_access(user_id=1)
        m = db.get(UserMembership, mid)
        saved = (m.start_at, m.end_at, m.original_end_at, m.checkout_key, m.terms_snapshot)
    result = execute(policy_api, mid, preview(policy_api, mid))
    assert result.status_code == 200, result.text
    with Session(policy_api[2]) as db:
        m = db.get(UserMembership, mid)
        assert m.user_id == 4 and (m.start_at, m.end_at, m.original_end_at, m.checkout_key, m.terms_snapshot) == saved
        assert db.scalar(select(func.count(UserMembership.id))) == 1
        assert db.scalar(select(func.count(MembershipPause.id))) == 1
        assert AccessService(db).get_today_access(user_id=1)['status'] == 'NO_ACCESS'
        with pytest.raises(Exception): AccessService(db).validate_checkin(gym_id=1, qr_token=old['qr_token'])
        received = AccessService(db).get_today_access(user_id=4)
        assert received['status'] == 'ACTIVE'
        assert AccessService(db).validate_checkin(gym_id=1, qr_token=received['qr_token'])['success']
    for uid, status in [(1, 'TRANSFERRED'), (4, 'ACTIVE')]:
        records = policy_api[0].get('/api/v1/memberships/me', headers=policy_api[1][uid]).json()
        assert records[0]['id'] == mid and records[0]['status'] == status
        assert records[0]['transfer']['eligible'] is False
        assert policy_api[0].post(f'/api/v1/memberships/me/{mid}/cancel', headers=policy_api[1][uid]).status_code in [404, 409]


def test_repeat_confirm_idempotent_but_transfer_again_fails(policy_api):
    mid = membership(policy_api); value = preview(policy_api, mid)
    first = execute(policy_api, mid, value)
    assert first.status_code == 200
    assert execute(policy_api, mid, value).json() == first.json()
    assert execute(policy_api, mid, value, 'different-key').status_code == 409
    with Session(policy_api[2]) as db:
        assert db.scalar(select(func.count(MembershipTransfer.id))) == 1
        with pytest.raises(Exception): transfer.preview(db, mid, 4, 'qr-1@example.test')


@pytest.mark.parametrize('change', ['single', 'expired', 'paused', 'suspended', 'unpaid', 'self', 'unknown', 'unverified', 'recipient_membership'])
def test_transfer_restrictions(policy_api, change):
    mid = membership(policy_api, 'SINGLE_GYM' if change == 'single' else 'MULTI_GYM')
    with Session(policy_api[2]) as db:
        m = db.get(UserMembership, mid)
        if change == 'expired': m.end_at = stored_instant(policy_api[3][0])
        if change == 'suspended': m.status = 'SUSPENDED'
        if change == 'unpaid': m.payment_status = 'FAILED'
        if change == 'unverified': db.get(User, 4).is_email_verified = False
        if change == 'paused':
            db.add(MembershipPause(membership_id=mid, request_key='active-pause', start_date=NOW.date(), end_date=NOW.date(), days=1, previous_end_at=m.end_at, new_end_at=m.end_at))
        if change == 'recipient_membership':
            db.add(UserMembership(user_id=4, gym_id=1, membership_type='SINGLE_GYM', status='ACTIVE', start_at=m.start_at, end_at=m.end_at, paid_amount=0, currency='INR', payment_status='PAID'))
        db.commit()
    with pytest.raises(Exception): preview(policy_api, mid, 'qr-1@example.test' if change == 'self' else 'missing@example.test' if change == 'unknown' else 'qr-4@example.test')
    with Session(policy_api[2]) as db:
        assert db.get(UserMembership, mid).user_id == 1
        assert db.scalar(select(func.count(MembershipTransfer.id))) == 0


def test_single_membership_cancellation_rejected_without_access_loss(policy_api):
    mid = membership(policy_api, 'SINGLE_GYM')
    result = policy_api[0].post(f'/api/v1/memberships/me/{mid}/cancel', headers=policy_api[1][1])
    assert result.status_code == 409
    with Session(policy_api[2]) as db:
        assert db.get(UserMembership, mid).status == 'ACTIVE'
        assert AccessService(db).get_today_access(user_id=1)['status'] == 'ACTIVE'


def test_used_day_is_not_reset_for_recipient(policy_api):
    mid = membership(policy_api)
    with Session(policy_api[2]) as db:
        qr = AccessService(db).get_today_access(user_id=1)
        assert AccessService(db).validate_checkin(gym_id=1, qr_token=qr['qr_token'])['success']
    assert execute(policy_api, mid, preview(policy_api, mid)).status_code == 200
    with Session(policy_api[2]) as db:
        assert AccessService(db).get_today_access(user_id=4)['status'] == 'USED'
        assert db.scalar(select(Checkin.user_id)) == 1
    policy_api[3][0] += timedelta(days=1)
    with Session(policy_api[2]) as db: assert AccessService(db).get_today_access(user_id=4)['status'] == 'ACTIVE'


def test_owner_and_admin_views_show_authoritative_credit(policy_api):
    from app.routers.gym_owner import router as owner_router
    from app.routers.admin import router as admin_router
    from app.core.security import create_access_token
    from app.models.auth import Role, UserRole
    policy_api[0].app.include_router(owner_router, prefix='/api/v1')
    policy_api[0].app.include_router(admin_router, prefix='/api/v1')
    with Session(policy_api[2]) as db:
        role = Role(name='ADMIN'); db.add(role); db.flush(); db.add(UserRole(user_id=5, role_id=role.id)); db.commit()
    bid = paid_booking(policy_api)
    response = policy_api[0].get(f'/api/v1/gym-owner/bookings/{bid}', headers=policy_api[1][2])
    assert response.status_code == 200 and response.json()['cancellation']['eligible'] is True
    policy_api[3][0] += timedelta(minutes=1)
    assert policy_api[0].post(f'/api/v1/gym-owner/bookings/{bid}/cancel', headers=policy_api[1][2], json={}).status_code == 409
    policy_api[3][0] -= timedelta(minutes=1)
    assert cancel_request(policy_api, bid).status_code == 200
    response = policy_api[0].get(f'/api/v1/admin/bookings/{bid}', headers={'Authorization': f'Bearer {create_access_token("5")}'})
    assert response.status_code == 200, response.text
    assert response.json()['cancellation']['wallet_transaction_id'] is not None


def test_transfer_token_expiry_tampering_and_role_authorization(policy_api):
    mid = membership(policy_api); value = preview(policy_api, mid)
    assert policy_api[0].post(f'/api/v1/memberships/me/{mid}/transfer', headers={**policy_api[1][2], 'Idempotency-Key': 'role-test-key'},
        json={'confirmation_token': value['confirmation_token'], 'confirmed': True}).status_code == 403
    assert execute(policy_api, mid, {'confirmation_token': value['confirmation_token'] + 'tampered'}).status_code == 400
    policy_api[3][0] += timedelta(minutes=6)
    assert execute(policy_api, mid, value).status_code == 400
    with Session(policy_api[2]) as db: assert db.get(UserMembership, mid).user_id == 1


def test_transfer_failure_is_atomic(policy_api, monkeypatch):
    mid = membership(policy_api); value = preview(policy_api, mid)
    with Session(policy_api[2]) as db: old_qr = AccessService(db).get_today_access(user_id=1)['qr_token']
    from app.services import notification_workflow
    monkeypatch.setattr(notification_workflow, 'publish', lambda *args: (_ for _ in ()).throw(RuntimeError('Synthetic publish failure')))
    with pytest.raises(RuntimeError): execute(policy_api, mid, value)
    with Session(policy_api[2]) as db:
        assert db.get(UserMembership, mid).user_id == 1
        assert db.scalar(select(func.count(MembershipTransfer.id))) == 0
        assert AccessService(db).validate_checkin(gym_id=1, qr_token=old_qr)['success']


def test_legacy_scanned_day_is_preserved_without_fabricating_a_checkin(policy_api):
    from app.models.membership import MembershipDailyAccess
    mid = membership(policy_api)
    with Session(policy_api[2]) as db:
        db.add(MembershipDailyAccess(user_id=1, gym_id=1, access_date=NOW.date(), status='SCANNED', scanned_at=stored_instant(policy_api[3][0])))
        db.commit()
    assert execute(policy_api, mid, preview(policy_api, mid)).status_code == 200
    with Session(policy_api[2]) as db:
        assert AccessService(db).get_today_access(user_id=4)['status'] == 'USED'
        assert db.scalar(select(func.count(Checkin.id))) == 0


def test_cancelled_booking_old_qr_and_new_issuance_are_blocked(policy_api, monkeypatch):
    from app.services import booking_access_service
    monkeypatch.setattr(booking_access_service, 'utcnow', lambda: policy_api[3][0])
    bid = paid_booking(policy_api)
    with Session(policy_api[2]) as db:
        old = booking_access_service.BookingAccessService(db).issue(bid, 1)['passes'][0]['qr_token']
    assert cancel_request(policy_api, bid).status_code == 200
    policy_api[3][0] += timedelta(hours=3)
    with Session(policy_api[2]) as db:
        with pytest.raises(Exception): AccessService(db).validate_checkin(gym_id=1, qr_token=old)
        with pytest.raises(Exception): booking_access_service.BookingAccessService(db).issue(bid, 1)