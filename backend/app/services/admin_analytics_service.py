"""Read-only booking analytics. Aggregate in SQL; never reconcile a payment here."""
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.reporting_range import reporting_range
from app.core.time import ist_today, utcnow
from app.models.booking import Booking, Payment
from app.models.gym import Gym
from app.models.payment_checkout import PaymentCheckout
from app.services.admin_revenue import gateway_booking_amount, eligible_admin_payment, admin_revenue_scope


COUNTS = ('bookings', 'places', 'confirmed', 'pending', 'cancelled', 'expired',
          'attended', 'no_show', 'paid_bookings', 'failed_payments', 'refunded_payments', 'review_required')


def blank():
    return {**{key: 0 for key in COUNTS}, 'paid_amount': Decimal('0')}


def merge(target, source):
    for key in (*COUNTS, 'paid_amount'):
        target[key] += source[key]


def present(row):
    total = row['bookings']
    return {**row, 'paid_amount': str(row['paid_amount']),
        'confirmation_rate': round(row['confirmed'] * 100 / total, 2) if total else None,
        'cancellation_rate': round(row['cancelled'] * 100 / total, 2) if total else None}


class AdminAnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    def report(self, *, date_from=None, date_to=None, grain='day', gym_id=None,
               country=None, state=None, city=None):
        first, last = reporting_range(date_from, date_to) or (ist_today() - timedelta(days=29), ist_today())
        if grain not in {'day', 'week', 'month'}:
            raise HTTPException(422, 'Unsupported analytics grain')
        days = (last - first).days + 1
        if first.toordinal() <= days:
            raise HTTPException(422, 'Date range cannot support a previous-period comparison')
        previous_first, previous_last = first - timedelta(days=days), first - timedelta(days=1)
        normalize = lambda column: func.coalesce(func.nullif(func.trim(column), ''), '')
        country_col, state_col, city_col = [normalize(col) for col in (Gym.country, Gym.state, Gym.city)]
        conditions = []
        for column, value in [(country_col, country), (state_col, state), (city_col, city)]:
            if value is not None:
                conditions.append(column == value.strip())
        if gym_id is not None:
            conditions.append(Gym.id == gym_id)
        gyms = self.db.execute(select(Gym.id, Gym.name, Gym.status, Gym.is_active,
            country_col.label('country'), state_col.label('state'), city_col.label('city'))
            .where(*conditions).order_by(Gym.name, Gym.id)).mappings().all()
        # Single payment row per booking at this boundary; aggregate defensively
        # before joining so payment/check-in multiplicity cannot inflate bookings.
        payments = select(Payment.booking_id,
            func.max(case((eligible_admin_payment(), gateway_booking_amount(self.db)), else_=0)).label('paid_amount'),
            func.max(case((eligible_admin_payment(), 1), else_=0)).label('paid'),
            func.max(case((Payment.status == 'FAILED', 1), else_=0)).label('failed'),
            func.max(case((Payment.status.in_(['REFUNDED', 'PARTIALLY_REFUNDED']), 1), else_=0)).label('refunded')
            ).join(Booking, Booking.id == Payment.booking_id).join(Gym, Gym.id == Booking.gym_id)
        payments = payments.where(Booking.slot_date.between(previous_first, last), *conditions).group_by(Payment.booking_id).subquery()
        review = select(PaymentCheckout.id).where(PaymentCheckout.id == Booking.checkout_id,
            PaymentCheckout.user_id == Booking.user_id, PaymentCheckout.status == 'REVIEW_REQUIRED').exists()
        expressions = [func.count(Booking.id).label('bookings'), func.coalesce(func.sum(Booking.quantity), 0).label('places')]
        for key, predicate in [('confirmed', Booking.status == 'CONFIRMED'), ('pending', Booking.status == 'PENDING_PAYMENT'),
                ('cancelled', Booking.status == 'CANCELLED'), ('expired', Booking.status == 'EXPIRED'),
                ('attended', Booking.attendance_status == 'ATTENDED'), ('no_show', Booking.attendance_status == 'NO_SHOW'),
                ('paid_bookings', payments.c.paid == 1), ('failed_payments', payments.c.failed == 1),
                ('refunded_payments', payments.c.refunded == 1), ('review_required', review)]:
            expressions.append(func.coalesce(func.sum(case((predicate, 1), else_=0)), 0).label(key))
        expressions.append(func.coalesce(func.sum(payments.c.paid_amount), 0).label('paid_amount'))
        # At most one row per gym/day, rather than loading every customer booking.
        daily = self.db.execute(select(Booking.gym_id, Booking.slot_date, *expressions)
            .join(Gym, Gym.id == Booking.gym_id).outerjoin(payments, payments.c.booking_id == Booking.id)
            .where(Booking.slot_date.between(previous_first, last), *conditions)
            .group_by(Booking.gym_id, Booking.slot_date)).mappings().all()
        overall, previous = blank(), blank()
        by_gym = {g['id']: {**dict(g), **blank()} for g in gyms}
        by_day = {first + timedelta(days=i): blank() for i in range(days)}
        for row in daily:
            metrics = {key: int(row[key] or 0) for key in COUNTS}
            metrics['paid_amount'] = Decimal(str(row['paid_amount'] or 0))
            if row['slot_date'] < first:
                merge(previous, metrics)
            else:
                merge(overall, metrics)
                merge(by_gym[row['gym_id']], metrics)
                merge(by_day[row['slot_date']], metrics)
        unique = self.db.execute(select(Booking.gym_id, func.count(func.distinct(Booking.user_id)))
            .join(Gym, Gym.id == Booking.gym_id).where(Booking.slot_date.between(first, last), *conditions)
            .group_by(Booking.gym_id)).all()
        for g in by_gym.values():
            g['unique_customers'] = 0
        for identifier, count in unique:
            by_gym[identifier]['unique_customers'] = count
        for target, start, end in [(overall, first, last), (previous, previous_first, previous_last)]:
            target['unique_customers'] = self.db.scalar(select(func.count(func.distinct(Booking.user_id)))
                .join(Gym, Gym.id == Booking.gym_id).where(Booking.slot_date.between(start, end), *conditions)) or 0
        locations = {}
        for g in by_gym.values():
            key = (g['country'], g['state'], g['city'])
            if key not in locations:
                locations[key] = {**blank(), 'country': key[0], 'state': key[1], 'city': key[2], 'gyms': 0, 'active_gyms': 0}
            locations[key]['gyms'] += 1
            locations[key]['active_gyms'] += int(g['is_active'] and g['status'] == 'APPROVED')
            merge(locations[key], g)
        buckets = {}
        for day, metrics in by_day.items():
            key = day if grain == 'day' else day - timedelta(days=day.weekday()) if grain == 'week' else day.replace(day=1)
            if key not in buckets:
                buckets[key] = {**blank(), 'period': key.isoformat(), 'date_from': day.isoformat(), 'date_to': day.isoformat()}
            buckets[key]['date_to'] = day.isoformat()
            merge(buckets[key], metrics)
        # Full catalog options, independent of date activity and current filter.
        options = self.db.execute(select(Gym.id, Gym.name, country_col.label('country'),
            state_col.label('state'), city_col.label('city')).order_by(Gym.name, Gym.id)).mappings().all()
        return {'date_from': str(first), 'date_to': str(last), 'grain': grain, 'timezone': 'Asia/Kolkata',
            'generated_at': utcnow().isoformat(), 'scope': admin_revenue_scope(),
            'filters': {'gym_id': gym_id, 'country': country, 'state': state, 'city': city},
            'catalog': {'gyms': len(gyms), 'active_gyms': sum(g['is_active'] and g['status'] == 'APPROVED' for g in gyms),
                'gyms_with_bookings': sum(g['bookings'] > 0 for g in by_gym.values())},
            'summary': present(overall), 'previous': {'date_from': str(previous_first), 'date_to': str(previous_last), **present(previous)},
            'series': [present(row) for row in buckets.values()],
            'gyms': [present(row) for row in sorted(by_gym.values(), key=lambda g: (-g['bookings'], g['name'], g['id']))],
            'locations': [present(row) for _, row in sorted(locations.items())],
            'options': [dict(row) for row in options]}