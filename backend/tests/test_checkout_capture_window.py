"""A gateway callback may cross visit start, never the original payment/visit end."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.time import stored_instant
from app.models.booking import Booking, Payment
from app.models.access import AccessQrToken
from app.services import booking_time, payment_checkout_service
from test_cashfree_payments import api, razorpay_api, booking_api, source_for, checkout, refresh, NOW


@pytest.mark.parametrize('provider_fixture', ['api', 'razorpay_api'])
@pytest.mark.parametrize('outcome', ['crossed_start', 'deadline_expired', 'visit_ended', 'cancelled'])
def test_capture_window_preserves_safe_confirmation(request, monkeypatch, provider_fixture, outcome):
    context = request.getfixturevalue(provider_fixture)
    now = [NOW.replace(hour=9, minute=59)]
    class Clock(datetime):
        @classmethod
        def utcnow(cls):
            return stored_instant(now[0])
    monkeypatch.setattr(payment_checkout_service, 'datetime', Clock)
    monkeypatch.setattr(booking_time, 'utcnow', lambda: now[0])
    record = checkout(context, source_for(context, 'CART'))
    assert record['can_pay']
    now[0] = NOW.replace(hour=10, minute=1)
    if outcome == 'deadline_expired':
        now[0] = NOW.replace(hour=10, minute=15)
    if outcome == 'visit_ended':
        now[0] = NOW.replace(hour=11, minute=1)
        with Session(context[2]) as db:
            # Isolate visit-end protection from the separately tested deadline.
            db.get(Booking, record['booking_ids'][0]).expires_at = stored_instant(now[0]) + timedelta(minutes=5)
            db.commit()
    if outcome == 'cancelled':
        with Session(context[2]) as db:
            db.get(Booking, record['booking_ids'][0]).status = 'CANCELLED'
            db.commit()
    assert not refresh(context, record).json()['can_pay']  # No NEW launch after start.
    context[3].pay(record)
    for _ in range(2):
        result = refresh(context, record).json()
        assert result['status'] == ('PAID' if outcome == 'crossed_start' else 'REVIEW_REQUIRED')
    with Session(context[2]) as db:
        booking = db.get(Booking, record['booking_ids'][0])
        assert (booking.status == 'CONFIRMED') == (outcome == 'crossed_start')
        assert db.scalar(select(Payment.status).where(Payment.booking_id == booking.id)) == 'PAID'
        assert db.scalar(select(func.count(AccessQrToken.id))) == (2 if outcome == 'crossed_start' else 0)