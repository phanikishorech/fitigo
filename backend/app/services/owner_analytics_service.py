"""Bounded SQL aggregations and paginated owner reports; no new accounting ledger."""
from datetime import timedelta
from sqlalchemy import and_, case, func, select
from app.core.reporting_range import reporting_range
from app.core.time import as_ist, ist_day_bounds, ist_today, ist_now
from app.models.auth import User
from app.models.booking import Booking, Payment
from app.models.gym import Gym
from app.models.slot import GymSlot
from app.services.owner_dashboard_service import OwnerDashboardService
from app.services.owner_metric_rules import booking_category
from app.services.owner_revenue import sales_query


class OwnerAnalyticsService(OwnerDashboardService):
    def period(self, first, last):
        return reporting_range(first, last) or (ist_today(), ist_today())

    def overview(self, owner_user_id, gym_id=None, date_from=None, date_to=None):
        first, last = self.period(date_from, date_to)
        scope = self._scope(owner_user_id, gym_id)
        summary = self.summary(owner_user_id=owner_user_id, gym_id=gym_id, date_from=first, date_to=last)
        # Up to 90 daily or 53 weekly buckets; aggregate on the server, not in JS.
        width = 1 if (last - first).days < 90 else 7
        buckets = [(first + timedelta(days=i), min(last, first + timedelta(days=i + width - 1)))
                   for i in range(0, (last - first).days + 1, width)]
        visits = self._visits(scope, first, last)
        sales = sales_query(scope, first, last)
        visit_columns, revenue_columns = [], []
        for index, (start, end) in enumerate(buckets):
            low, high = ist_day_bounds(start)[0], ist_day_bounds(end)[1]
            visit_columns.append(func.count(case((and_(visits.c.recorded_at >= low, visits.c.recorded_at < high), 1))).label(f'b{index}'))
            revenue_columns.append(func.coalesce(func.sum(case((and_(sales.c.recorded_at >= low, sales.c.recorded_at < high), sales.c.recognized_amount), else_=0)), 0).label(f'b{index}'))
        visit_values = self.db.execute(select(*visit_columns)).one()
        revenue_values = self.db.execute(select(*revenue_columns)).one()
        by_gym = self.db.execute(select(sales.c.gym_id, sales.c.gym_name,
            func.sum(sales.c.recognized_amount).label('total'),
            func.sum(case((sales.c.category == 'single_gym_membership', sales.c.recognized_amount), else_=0)).label('single'),
            func.sum(case((sales.c.category == 'individual_booking', sales.c.recognized_amount), else_=0)).label('booking'))
            .group_by(sales.c.gym_id, sales.c.gym_name).order_by(sales.c.gym_name, sales.c.gym_id)).all()
        return {'summary': summary, 'grouping': 'daily' if width == 1 else 'weekly',
            'series': [{'date': str(start), 'date_to': str(end), 'visits': int(visit_values[i]), 'revenue': str(revenue_values[i])}
                       for i, (start, end) in enumerate(buckets)],
            'revenue_by_gym': [{'gym_id': r.gym_id, 'gym_name': r.gym_name, 'total': str(r.total),
                'single_gym_membership': str(r.single), 'individual_booking': str(r.booking)} for r in by_gym]}

    def page(self, query, limit, offset):
        total = self.db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
        return self.db.execute(query.limit(limit).offset(offset)).mappings().all(), int(total)

    def bookings(self, owner_user_id, gym_id=None, date_from=None, date_to=None, category=None, limit=20, offset=0):
        first, last = self.period(date_from, date_to)
        scope = self._scope(owner_user_id, gym_id)
        classification = booking_category(ist_now())
        query = select(Booking.id, Booking.gym_id, Gym.name.label('gym_name'), Booking.slot_date,
            GymSlot.start_time, GymSlot.end_time, GymSlot.name.label('slot_name'), Booking.visitor_names,
            Booking.access_source, Booking.quantity, Booking.total_price, Booking.currency, Booking.status,
            Booking.attendance_status, classification.label('category'), User.first_name, User.last_name,
            Payment.status.label('payment_status')).select_from(Booking)
        query = query.join(Gym, Gym.id == Booking.gym_id).join(GymSlot, GymSlot.id == Booking.gym_slot_id)
        query = query.join(User, User.id == Booking.user_id).outerjoin(Payment, Payment.booking_id == Booking.id)
        query = query.where(scope, Booking.slot_date.between(first, last))
        if category:
            query = query.where(classification == category)
        rows, total = self.page(query.order_by(Booking.slot_date.desc(), GymSlot.start_time.desc(), Booking.id.desc()), limit, offset)
        return {'total': total, 'items': [{**{k: r[k] for k in ['id', 'gym_id', 'gym_name', 'slot_name', 'access_source', 'quantity', 'currency', 'status', 'attendance_status', 'category', 'payment_status']},
            'date': str(r['slot_date']), 'start_time': str(r['start_time']), 'end_time': str(r['end_time']),
            'amount': str(r['total_price']), 'customer': ' '.join(filter(None, [r['first_name'], r['last_name']])) or 'Customer',
            'visitors': r['visitor_names'] or []} for r in rows]}

    def transactions(self, owner_user_id, gym_id=None, date_from=None, date_to=None, category=None, payment_status=None, limit=20, offset=0):
        first, last = self.period(date_from, date_to)
        sales = sales_query(self._scope(owner_user_id, gym_id), first, last)
        query = select(sales)
        if category:
            query = query.where(sales.c.category == category)
        if payment_status:
            query = query.where(sales.c.payment_status == payment_status)
        rows, total = self.page(query.order_by(sales.c.recorded_at.desc(), sales.c.category, sales.c.record_id.desc()), limit, offset)
        return {'total': total, 'items': [{**{k: r[k] for k in ['record_id', 'category', 'gym_id', 'gym_name', 'payment_status', 'checkout_status', 'currency', 'mode', 'booking_id', 'provider', 'transaction_id', 'exclusion_reason']},
            'id': f"{r['category']}:{r['record_id']}", 'recorded_at': as_ist(r['recorded_at']).isoformat(),
            'amount': str(r['amount']), 'recognized_amount': str(r['recognized_amount']), 'included': bool(r['included'])} for r in rows]}

    def attendance_page(self, owner_user_id, gym_id=None, date_from=None, date_to=None, limit=20, offset=0):
        first, last = self.period(date_from, date_to)
        visits = self._visits(self._scope(owner_user_id, gym_id), first, last)
        query = select(visits, Gym.name.label('gym_name'), User.first_name, User.last_name)
        query = query.join(Gym, Gym.id == visits.c.gym_id).join(User, User.id == visits.c.user_id)
        rows, total = self.page(query.order_by(visits.c.recorded_at.desc(), visits.c.record_id.desc()), limit, offset)
        return {'total': total, 'items': [{'id': r['record_id'], 'gym_name': r['gym_name'], 'booking_id': r['booking_id'],
            'category': r['category'], 'recorded_at': as_ist(r['recorded_at']).isoformat(),
            'customer': r['visitor_name'] or ' '.join(filter(None, [r['first_name'], r['last_name']])) or 'Customer'} for r in rows]}