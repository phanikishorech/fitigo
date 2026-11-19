"""Acceptance invariants using existing disposable MySQL fixtures only."""
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.access import Checkin
from app.models.booking import Payment
from app.models.payment_checkout import PaymentAttempt, PaymentCheckout
from app.services.admin_business import summary
from test_admin_business_cleanup import evidence
from test_admin_financial_position import AT, DAY, verified
from test_owner_dashboard_mysql import mysql_api, pytestmark


@pytest.mark.parametrize('kind', ['BOOKING', 'CART', 'SINGLE_GYM', 'MULTI_GYM'])
def test_collections_require_fulfilled_purchase_not_just_paid_order(mysql_api, kind):
    with Session(mysql_api[2]) as db:
        checkout = PaymentCheckout(id=str(uuid4()), user_id=3, source_key=uuid4().hex,
            kind=kind, mode='test', provider='RAZORPAY', key_id='fixture', amount=150,
            currency='INR', snapshot={}, status='PAID', gateway_payment_id='pay_'+uuid4().hex,
            created_at=AT)
        db.add(checkout); db.flush()
        db.add(PaymentAttempt(id=str(uuid4()), checkout_id=checkout.id,
            external_id=checkout.gateway_payment_id, status='SUCCESS', amount=150,
            currency='INR', refunded_amount=0))
        evidence(db, checkout); db.commit()
        result = summary(db, date_from=DAY, date_to=DAY, mode='test')
        assert result['collections']['total'] == '0.00'


def test_collection_date_ist_boundaries_and_gym_environment_isolation(mysql_api):
    from app.core.time import ist_day_bounds
    start, end = [value.replace(tzinfo=None) for value in ist_day_bounds(DAY)]
    with Session(mysql_api[2]) as db:
        for at, gym, mode in [(start-timedelta(seconds=1),1,'test'), (start,1,'test'),
                (end-timedelta(seconds=1),1,'test'), (end,1,'test'), (start,2,'test'), (start,1,'live')]:
            _, checkout = verified(db, gym=gym, mode=mode, at=at)
            evidence(db, checkout, at)
        db.commit()
        result = summary(db, date_from=DAY, date_to=DAY, mode='test', gym_id=1)
        assert result['collections']['total'] == '300.00'
        assert result['series'][0]['individual_collections'] == '300.00'
        assert summary(db, date_from=DAY, date_to=DAY, mode='live', gym_id=1)['collections']['total'] == '150.00'


def test_large_collection_cohort_matches_database_and_does_not_invent_earnings(mysql_api):
    with Session(mysql_api[2]) as db:
        for _ in range(150):
            _, checkout = verified(db)
            evidence(db, checkout)
        db.commit()
        result = summary(db, date_from=DAY, date_to=DAY, mode='test')
        assert Decimal(result['collections']['total']) == db.scalar(select(func.sum(Payment.amount)))
        assert result['collections']['total'] == '22500.00'
        assert result['collections']['fitigo_commission'] is None
        assert result['visits']['no_shows'] == 0
        assert db.scalar(select(func.count(Checkin.id))) == 0