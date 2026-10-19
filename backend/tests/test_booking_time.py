"""Past-time reservations/debits must fail atomically; isolated SQLite only."""
from app.core.time import IST, stored_instant
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_booking_access_qr import api, NOW
from app.models.access import AccessQrToken
from app.models.booking import Booking, Payment
from app.models.cart import CartItem
from app.models.class_booking import GymClass, ClassSession
from app.models.gym import Gym
from app.models.slot import GymSlot, SlotAvailability
from app.models.wallet import WalletAccount, WalletTransaction
from app.services import booking_time
from app.services.booking_time import require_future_start
from app.services.booking_service import BookingService
from app.services.admin_booking_ops_service import AdminBookingOpsService


@pytest.fixture
def clock(api, monkeypatch):
    current = [NOW]
    monkeypatch.setattr(booking_time, "utcnow", lambda: current[0])
    monkeypatch.setattr(BookingService, "_now", lambda self: stored_instant(current[0]))
    return current


def gym_body(day=None, start="13:00", end="14:00"):
    return {"gym_id": 1, "booking_date": (day or NOW.date()).isoformat(),
            "preferred_start_time": start, "preferred_end_time": end,
            "member_count": 1, "visitor_names": ["David"]}


def snapshot(engine):
    with Session(engine) as db:
        return (db.scalar(select(WalletAccount.balance).where(WalletAccount.user_id == 1)),
                tuple(db.scalar(select(func.count(model.id))) for model in (Booking, Payment, AccessQrToken, WalletTransaction)),
                tuple(db.execute(select(ClassSession.id, ClassSession.booked_capacity)).all()))


def assert_past(response):
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "BOOKING_TIME_PASSED"


@pytest.mark.parametrize("day,start", [(date(2026, 10, 9), "13:00"), (NOW.date(), "11:00"), (NOW.date(), "12:00")])
def test_add_gym_rejects_past_date_past_start_and_exact_boundary(api, clock, day, start):
    client, headers, engine = api
    before = snapshot(engine)
    assert_past(client.post("/api/v1/cart/items/gym", headers=headers[1], json=gym_body(day, start)))
    assert snapshot(engine) == before
    with Session(engine) as db:
        assert db.scalar(select(func.count(CartItem.id))) == 0


@pytest.mark.parametrize("checkout", ["/checkout", "/checkout/wallet"])
@pytest.mark.parametrize("advance", [timedelta(hours=1), timedelta(days=1)])
def test_stale_cart_is_rechecked_at_checkout_without_debit(api, clock, checkout, advance):
    client, headers, engine = api
    assert client.post("/api/v1/cart/items/gym", headers=headers[1], json=gym_body()).status_code == 200
    before = snapshot(engine)
    clock[0] += advance
    assert_past(client.post("/api/v1/cart" + checkout, headers=headers[1]))
    assert snapshot(engine) == before
    with Session(engine) as db:
        assert db.scalars(select(CartItem)).one().status == "ACTIVE"


def add_class(api, start=time(13), day=None):
    with Session(api[2]) as db:
        db.get(Gym, 1).has_classes = True
        group = GymClass(gym_id=1, class_name="Test class", is_active=True)
        db.add(group); db.flush()
        session = ClassSession(gym_class_id=group.id, session_date=day or NOW.date(),
            start_time=start, end_time=time(15), maximum_capacity=10, booked_capacity=0,
            price_per_person=100, status="AVAILABLE")
        db.add(session); db.commit()
        return {"booking_type": "CLASS", "gym_id": 1, "booking_date": session.session_date.isoformat(),
                "class_session_id": session.id, "member_count": 1, "visitor_names": ["David"]}


@pytest.mark.parametrize("day,start", [(NOW.date() - timedelta(days=1), time(13)), (NOW.date(), time(11)), (NOW.date(), time(12))])
def test_add_class_rejects_elapsed_session(api, clock, day, start):
    body = add_class(api, start, day)
    before = snapshot(api[2])
    assert_past(api[0].post("/api/v1/cart/items/class", headers=api[1][1], json=body))
    assert snapshot(api[2]) == before


@pytest.mark.parametrize("checkout", ["/checkout", "/checkout/wallet"])
def test_mixed_basket_rolls_back_capacity_and_money_when_one_item_expired(api, clock, checkout):
    client, headers, engine = api
    body = add_class(api, time(14))
    assert client.post("/api/v1/cart/items/class", headers=headers[1], json=body).status_code == 200
    assert client.post("/api/v1/cart/items/gym", headers=headers[1], json=gym_body()).status_code == 200
    before = snapshot(engine)
    clock[0] = NOW.replace(hour=13)
    assert_past(client.post("/api/v1/cart" + checkout, headers=headers[1]))
    assert snapshot(engine) == before
    with Session(engine) as db:
        assert all(item.status == "ACTIVE" for item in db.scalars(select(CartItem)))


def test_stale_class_checkout_does_not_reserve_capacity_or_debit(api, clock):
    client, headers, engine = api
    body = add_class(api)
    assert client.post("/api/v1/cart/items/class", headers=headers[1], json=body).status_code == 200
    before = snapshot(engine)
    clock[0] = NOW.replace(hour=13)
    assert_past(client.post("/api/v1/cart/checkout/wallet", headers=headers[1]))
    assert snapshot(engine) == before


def test_expiry_during_checkout_rolls_back_even_flushed_qr_and_payment(api, clock, monkeypatch):
    client, headers, engine = api
    assert client.post("/api/v1/cart/items/gym", headers=headers[1], json=gym_body()).status_code == 200
    before = snapshot(engine)
    from app.services.booking_access_service import BookingAccessService
    original = BookingAccessService.ensure_records
    def create_then_advance(self, booking):
        original(self, booking)
        clock[0] = NOW.replace(hour=13)
    monkeypatch.setattr(BookingAccessService, "ensure_records", create_then_advance)
    assert_past(client.post("/api/v1/cart/checkout/wallet", headers=headers[1]))
    assert snapshot(engine) == before


@pytest.mark.parametrize("day", [NOW.date() - timedelta(days=1), NOW.date()])
def test_direct_booking_cannot_bypass_past_time_policy(api, clock, day):
    before = snapshot(api[2])
    response = api[0].post("/api/v1/bookings", headers=api[1][1], json={
        "gym_slot_id": 1, "slot_date": day.isoformat(), "quantity": 1, "visitor_names": ["David"]})
    assert_past(response)
    assert snapshot(api[2]) == before
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(SlotAvailability.id))) == 0


@pytest.mark.parametrize("admin", [False, True])
def test_pending_booking_cannot_be_paid_after_visit_starts(api, clock, admin):
    client, headers, engine = api
    clock[0] = NOW.replace(hour=9, minute=59)
    response = client.post("/api/v1/bookings", headers=headers[1], json={
        "gym_slot_id": 1, "slot_date": NOW.date().isoformat(), "quantity": 1, "visitor_names": ["David"]})
    assert response.status_code == 200, response.text
    booking_id = response.json()["id"]
    before = snapshot(engine)
    clock[0] = NOW.replace(hour=10)
    if admin:
        with Session(engine) as db:
            with pytest.raises(HTTPException) as error:
                AdminBookingOpsService(db).update_payment_status(booking_id=booking_id, new_status="PAID")
            assert error.value.detail["code"] == "BOOKING_TIME_PASSED"
    else:
        assert_past(client.post(f"/api/v1/bookings/{booking_id}/pay", headers=headers[1]))
    assert snapshot(engine) == before
    with Session(engine) as db:
        assert db.get(Booking, booking_id).status == "PENDING_PAYMENT"
        assert db.scalars(select(Payment)).one().status == "INITIATED"


def test_reschedule_to_past_time_does_not_move_capacity(api, clock):
    client, headers, engine = api
    future = NOW.date() + timedelta(days=1)
    response = client.post("/api/v1/bookings", headers=headers[1], json={"gym_slot_id": 1, "slot_date": future.isoformat(), "quantity": 1})
    assert response.status_code == 200, response.text
    booking_id = response.json()["id"]
    assert_past(client.post(f"/api/v1/bookings/{booking_id}/reschedule", headers=headers[1], json={"gym_slot_id": 1, "slot_date": NOW.date().isoformat()}))
    with Session(engine) as db:
        assert db.get(Booking, booking_id).slot_date == future
        assert db.scalars(select(SlotAvailability)).one().booked_count == 1


@pytest.mark.parametrize("kind", ["gym", "class"])
def test_future_checkout_still_pays_once_and_creates_access(api, clock, kind):
    client, headers, engine = api
    body = gym_body() if kind == "gym" else add_class(api)
    assert client.post(f"/api/v1/cart/items/{kind}", headers=headers[1], json=body).status_code == 200
    response = client.post("/api/v1/cart/checkout/wallet", headers=headers[1])
    assert response.status_code == 200, response.text
    with Session(engine) as db:
        assert db.scalar(select(WalletAccount.balance)) == Decimal("9900")
        assert db.scalar(select(func.count(WalletTransaction.id))) == 1
        assert db.scalar(select(func.count(AccessQrToken.id))) == 1


def test_utc_midnight_naive_clock_and_offset_input():
    current = datetime(2026, 10, 8, 23, 59, 59, tzinfo=IST)
    require_future_start(date(2026, 10, 9), time(0), now=current)
    require_future_start(date(2026, 10, 9), time(0), now=stored_instant(current))
    with pytest.raises(HTTPException):
        require_future_start(date(2026, 10, 8), time(23, 59), now=current)
    with pytest.raises(HTTPException) as error:
        require_future_start(date(2026, 10, 9), time(12, tzinfo=timezone(timedelta(hours=5, minutes=30))), now=current)
    assert error.value.detail["code"] == "INVALID_BOOKING_TIME"


def test_legacy_availability_preview_rejects_past_time_before_writes(api, clock):
    from app.routers.gyms_public import validate_gym_booking
    from app.schemas.access_booking import ValidateBookingRequest
    from app.models.auth import User
    with Session(api[2]) as db:
        with pytest.raises(HTTPException) as error:
            validate_gym_booking(gym_id=1, payload=ValidateBookingRequest(
                access_type_id="DAY_PASS", gym_slot_id=1, slot_date=NOW.date(), quantity=1),
                db=db, current_user=db.get(User, 1))
        assert error.value.detail["code"] == "BOOKING_TIME_PASSED"
        assert db.scalar(select(func.count(SlotAvailability.id))) == 0


def test_new_free_membership_covered_reservation_cannot_use_past_slot(api, clock):
    with Session(api[2]) as db:
        with pytest.raises(HTTPException) as error:
            BookingService(db).create_booking(user_id=1, gym_slot_id=1, slot_date=NOW.date(), quantity=1,
                notes=None, unit_price_override=Decimal("0"), auto_confirm_if_free=True, access_source="MEMBERSHIP_ACCESS")
        assert error.value.detail["code"] == "BOOKING_TIME_PASSED"
        assert db.scalar(select(func.count(Booking.id))) == 0