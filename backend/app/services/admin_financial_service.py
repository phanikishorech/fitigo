"""Admin-only read models. Exact Decimal totals; unknown accounting is never zero.

Collections lack authoritative capture dates in the current schema. Do not use
created_at/first_seen_at as substitutes. No report initiates provider requests.
"""
from datetime import timedelta
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import and_, case, exists, func, literal, or_, select, text
from app.core.config import settings
from app.core.reporting_range import reporting_range
from app.core.time import as_ist, ist_day_bounds, ist_now, ist_today, utcnow
from app.models.auth import Role, User, UserRole
from app.models.access import Checkin
from app.models.booking import Booking
from app.models.customer_policy import BookingCancellation, MembershipTransfer
from app.models.gym import Gym
from app.models.membership import MembershipPause, UserMembership
from app.models.payment_checkout import PaymentAttempt, PaymentCheckout
from app.models.slot import GymSlot
from app.models.wallet import WalletAccount, WalletTransaction
from app.services.admin_financial_queries import attended_values, booking_values, paid_checkouts, visits


def amount(value):
    return str(Decimal(str(value or 0)).quantize(Decimal('.01')))


def missing(reason):
    return {'value': None, 'status': 'NOT_CONFIGURED', 'reason': reason}


def rate(numerator, denominator):
    return round(numerator * 100 / denominator, 2) if denominator else None


class AdminFinancialService:
    def __init__(self, db):
        self.db = db

    def total(self, query, column):
        rows = query.subquery()
        return self.db.scalar(select(func.coalesce(func.sum(rows.c[column]), 0))) or Decimal(0)

    def count(self, query):
        return self.db.scalar(select(func.count()).select_from(query.subquery())) or 0

    @staticmethod
    def source_filter(provider, gateway_column, wallet_column, source):
        if source == 'WALLET': return wallet_column > 0
        if source in {'RAZORPAY', 'CASHFREE'}: return and_(provider == source, gateway_column > 0)
        return literal(True)

    def payment_report(self, start, end, mode, gym_id, source):
        # Provider attempts, not booking allocation rows, are the cash evidence.
        # A refunded payment was collected first; expose both gross and reversal.
        attempts = select(PaymentAttempt.id, PaymentAttempt.external_id, PaymentAttempt.amount,
            PaymentAttempt.refunded_amount, PaymentAttempt.status, PaymentCheckout.provider,
            PaymentCheckout.kind, PaymentCheckout.amount.label('expected'),
            PaymentAttempt.first_seen_at, PaymentAttempt.checkout_id).join(PaymentCheckout,
                PaymentCheckout.id == PaymentAttempt.checkout_id).where(
                    PaymentCheckout.mode == mode, PaymentCheckout.currency == 'INR', PaymentAttempt.currency == 'INR',
                    PaymentCheckout.provider.in_(['RAZORPAY', 'CASHFREE']))
        # Cannot attribute cash from a cross-gym cart to one gym without a
        # verified transaction-level allocation. Do not count its whole charge.
        if gym_id is not None or source == 'WALLET':
            return {'applicable': False, 'reason': 'Gateway cash is not a wallet contribution; gym-level provider cash allocation is not recorded.',
                'dated_collections': missing('Authoritative capture dates are not stored.'), 'undated': [], 'attempts': {},
                'gateway_fee': missing('Actual provider fees are not recorded.'), 'mismatches': 0}
        if source: attempts = attempts.where(PaymentCheckout.provider == source)
        rows = attempts.subquery('provider_evidence')
        duplicates = select(rows.c.provider, rows.c.external_id).group_by(rows.c.provider, rows.c.external_id).having(func.count() > 1).subquery('duplicate_provider_ids')
        duplicate_count = self.count(select(duplicates))
        unique_cash = ~exists(select(duplicates.c.external_id).where(duplicates.c.provider == rows.c.provider,
            duplicates.c.external_id == rows.c.external_id))
        paid_states = rows.c.status.in_(['SUCCESS', 'REFUNDED', 'PARTIALLY_REFUNDED'])
        undated = []
        for provider in ('RAZORPAY', 'CASHFREE'):
            if source and source != provider: continue
            q = select(rows).where(rows.c.provider == provider, paid_states, unique_cash)
            gross, refunds = self.total(q, 'amount'), self.total(q, 'refunded_amount')
            membership_q = q.where(rows.c.kind.in_(['SINGLE_GYM', 'MULTI_GYM']))
            undated.append({'provider': provider, 'gross_collections': amount(gross), 'refunds_recorded': amount(refunds),
                'net_recorded': amount(gross-refunds), 'successful_payments': self.count(q),
                'membership_collections': amount(self.total(membership_q, 'amount')),
                'recharge_collections': amount(self.total(q.where(rows.c.kind == 'WALLET_TOPUP'), 'amount'))})
        # Explicit observation cohort, NOT collection-date metrics.
        counts = {state: self.count(select(rows).where(rows.c.status == state, rows.c.first_seen_at >= start,
            rows.c.first_seen_at < end)) for state in ('SUCCESS', 'REFUNDED', 'PARTIALLY_REFUNDED', 'PENDING', 'FAILED')}
        successful = sum(counts[state] for state in ('SUCCESS', 'REFUNDED', 'PARTIALLY_REFUNDED'))
        mismatches = self.count(select(rows).where(paid_states, or_(rows.c.amount != rows.c.expected,
            rows.c.refunded_amount > rows.c.amount, rows.c.amount < 0))) + duplicate_count
        return {'applicable': True, 'dated_collections': missing('Capture/refund event timestamps are not stored. Undated evidence is excluded from date-filtered collections.'),
            'undated': undated, 'attempts': {'total': sum(counts.values()), 'successful': successful,
                'pending': counts['PENDING'], 'failed': counts['FAILED'], 'success_rate': rate(successful, sum(counts.values())),
                'basis': 'First observed in selected period, current reconciled status; not capture-date collections.'},
            'gateway_fee': missing('Actual provider fees are not recorded.'), 'mismatches': mismatches,
            'duplicate_transaction_ids_excluded': duplicate_count,
            'review_required': self.count(select(PaymentCheckout.id).where(PaymentCheckout.mode == mode,
                PaymentCheckout.status == 'REVIEW_REQUIRED', PaymentCheckout.provider == source if source else literal(True)))}

    def wallet_report(self, start, end, mode, gym_id, source):
        if gym_id is not None or source in {'RAZORPAY', 'CASHFREE'}:
            return {'applicable': False, 'reason': 'Wallet liability is platform-wide. Remaining credits cannot be attributed to a gym or original provider without credit-consumption allocations.',
                'outstanding': None, 'stored_balance': None, 'credits': None, 'spending': None}
        signed = case((WalletTransaction.direction == 'IN', WalletTransaction.amount),
            (WalletTransaction.direction == 'OUT', -WalletTransaction.amount), else_=0)
        ledger = select(WalletTransaction.account_id, func.sum(signed).label('balance'),
            func.sum(case((or_(WalletTransaction.direction.not_in(['IN', 'OUT']), WalletTransaction.amount < 0), 1), else_=0)).label('invalid'))
        ledger = ledger.where(WalletTransaction.currency == 'INR').group_by(WalletTransaction.account_id).subquery('wallet_net')
        malformed = exists(select(WalletTransaction.id).where(WalletTransaction.account_id == WalletAccount.id,
            or_(WalletTransaction.currency != WalletAccount.currency, WalletTransaction.user_id != WalletAccount.user_id)))
        accounts = select(WalletAccount.id, WalletAccount.user_id, WalletAccount.balance.label('stored'),
            func.coalesce(ledger.c.balance, 0).label('ledger'),
            (func.coalesce(ledger.c.invalid, 0) + case((malformed, 1), else_=0)).label('invalid')).outerjoin(
                ledger, ledger.c.account_id == WalletAccount.id).where(WalletAccount.payment_mode == mode, WalletAccount.currency == 'INR').subquery('wallet_reconciliation')
        totals = self.db.execute(select(func.coalesce(func.sum(accounts.c.stored), 0), func.coalesce(func.sum(accounts.c.ledger), 0),
            func.coalesce(func.sum(case((or_(accounts.c.stored != accounts.c.ledger, accounts.c.invalid > 0,
                accounts.c.ledger < 0), 1), else_=0)), 0))).one()
        stored, net, mismatches = totals
        review_accounts = [dict(account_id=row.id, user_id=row.user_id, stored_balance=amount(row.stored),
            ledger_net=amount(row.ledger), invalid_records=int(row.invalid)) for row in self.db.execute(
                select(accounts).where(or_(accounts.c.stored != accounts.c.ledger, accounts.c.invalid > 0, accounts.c.ledger < 0)))]
        movements = select(WalletTransaction).join(WalletAccount, WalletAccount.id == WalletTransaction.account_id).where(
            WalletAccount.payment_mode == mode, WalletAccount.currency == 'INR', WalletTransaction.currency == 'INR',
            WalletTransaction.created_at >= start, WalletTransaction.created_at < end)
        categories = list(self.db.execute(select(WalletTransaction.txn_type, WalletTransaction.direction,
            func.sum(WalletTransaction.amount).label('amount'), func.count().label('count')).join(WalletAccount,
                WalletAccount.id == WalletTransaction.account_id).where(WalletAccount.payment_mode == mode,
                    WalletAccount.currency == 'INR', WalletTransaction.currency == 'INR',
                    WalletTransaction.created_at >= start, WalletTransaction.created_at < end).group_by(
                        WalletTransaction.txn_type, WalletTransaction.direction)).mappings())
        credit = self.total(movements.where(WalletTransaction.direction == 'IN'), 'amount')
        debit = self.total(movements.where(WalletTransaction.direction == 'OUT'), 'amount')
        spending = self.total(movements.where(WalletTransaction.direction == 'OUT', WalletTransaction.txn_type == 'PAYMENT'), 'amount')
        linked_bookings = exists(select(Booking.id).where(Booking.checkout_id == WalletTransaction.checkout_id))
        linked_membership = exists(select(UserMembership.id).where(or_(
            UserMembership.wallet_transaction_id == WalletTransaction.id,
            UserMembership.gateway_checkout_id == WalletTransaction.checkout_id)))
        payment_movements = movements.where(WalletTransaction.direction == 'OUT', WalletTransaction.txn_type == 'PAYMENT')
        booking_spend = self.total(payment_movements.where(linked_bookings, ~linked_membership), 'amount')
        member_spend = self.total(payment_movements.where(linked_membership, ~linked_bookings), 'amount')
        prior = select(WalletTransaction).join(WalletAccount, WalletAccount.id == WalletTransaction.account_id).where(
            WalletAccount.payment_mode == mode, WalletAccount.currency == 'INR', WalletTransaction.currency == 'INR')
        def net_before(moment):
            data = prior.where(WalletTransaction.created_at < moment).subquery()
            return self.db.scalar(select(func.coalesce(func.sum(case((data.c.direction == 'IN', data.c.amount),
                (data.c.direction == 'OUT', -data.c.amount), else_=0)), 0)))
        rows = movements.subquery('period_wallet')
        day = func.date(func.datetime(rows.c.created_at, '+330 minutes')) if self.db.bind.dialect.name == 'sqlite' else func.date(func.date_add(rows.c.created_at, text('INTERVAL 330 MINUTE')))
        series = [dict(r) for r in self.db.execute(select(day.label('day'),
            func.sum(case((rows.c.direction == 'IN', rows.c.amount), else_=0)).label('credits'),
            func.sum(case((and_(rows.c.direction == 'OUT', rows.c.txn_type == 'PAYMENT'), rows.c.amount), else_=0)).label('spending')).group_by(day)).mappings()]
        unknown = self.db.scalar(select(func.coalesce(func.sum(WalletAccount.balance), 0)).where(
            WalletAccount.payment_mode.is_(None), WalletAccount.currency == 'INR'))
        return {'applicable': True, 'outstanding': amount(net) if not mismatches else None,
            'reason': f'{int(mismatches)} wallet account(s) have mismatched balances, invalid ledger records or negative ledger balances. Review the listed accounts; no balance was estimated.' if mismatches else None,
            'review_accounts': review_accounts,
            'ledger_net': amount(net), 'stored_balance': amount(stored), 'reconciliation_difference': amount(stored-net),
            'mismatched_accounts': int(mismatches), 'status': 'RECONCILED' if not mismatches else 'REVIEW_REQUIRED',
            'unclassified_mode_balance': amount(unknown), 'credits': amount(credit), 'debits': amount(debit), 'spending': amount(spending),
            'booking_spending': amount(booking_spend), 'membership_spending': amount(member_spend),
            'unallocated_spending': amount(spending-booking_spend-member_spend),
            'cancellation_credits': amount(sum((r['amount'] for r in categories if r['txn_type']=='CANCELLATION_CREDIT' and r['direction']=='IN'), Decimal(0))),
            'opening_ledger_balance': amount(net_before(start)), 'closing_ledger_balance': amount(net_before(end)),
            'movements_by_type': [dict(r, amount=amount(r['amount'])) for r in categories], 'series': series,
            'promotional_credits': missing('No approved promotional credit classification exists.'),
            'adjustments': missing('No approved wallet-adjustment taxonomy/workflow exists; recorded transaction types remain visible.'),
            'expirations': missing('Wallet expiration is not implemented.'),
            'source_liability': missing('Debits are not allocated to original credits. FIFO is not assumed.'),
            'liability_aging': missing('Remaining credit lots and their consumption order are not recorded.')}

    def wallet_ledger(self, *, date_from=None, date_to=None, mode=None, direction=None, txn_type=None, limit=50, offset=0):
        first, last = reporting_range(date_from, date_to) or (ist_today()-timedelta(days=29), ist_today())
        mode = mode or settings.gateway_mode
        if mode not in {'test', 'live'} or direction not in {None, 'IN', 'OUT'}: raise HTTPException(422, 'Invalid ledger filter')
        start, end = ist_day_bounds(first)[0].replace(tzinfo=None), ist_day_bounds(last)[1].replace(tzinfo=None)
        query = select(WalletTransaction).join(WalletAccount, WalletAccount.id == WalletTransaction.account_id).where(
            WalletAccount.payment_mode == mode, WalletTransaction.currency == 'INR', WalletAccount.currency == 'INR',
            WalletTransaction.created_at >= start, WalletTransaction.created_at < end)
        if direction: query = query.where(WalletTransaction.direction == direction)
        if txn_type: query = query.where(WalletTransaction.txn_type == txn_type)
        count = self.count(query)
        rows = self.db.scalars(query.order_by(WalletTransaction.created_at.desc(), WalletTransaction.id.desc()).limit(limit).offset(offset))
        return {'total': count, 'mode': mode, 'date_from': str(first), 'date_to': str(last),
            'items': [{'id': r.id, 'account_id': r.account_id, 'direction': r.direction, 'txn_type': r.txn_type,
                'amount': amount(r.amount), 'currency': r.currency, 'checkout_id': r.checkout_id,
                'reference': r.reference, 'created_at': as_ist(r.created_at).isoformat()} for r in rows]}

    def report(self, *, date_from=None, date_to=None, gym_id=None, mode=None, source=None):
        first, last = reporting_range(date_from, date_to) or (ist_today() - timedelta(days=29), ist_today())
        mode = mode or settings.gateway_mode
        if mode not in {'test', 'live'} or source not in {None, 'RAZORPAY', 'CASHFREE', 'WALLET'}:
            raise HTTPException(422, 'Invalid financial filter')
        if gym_id is not None and not self.db.get(Gym, gym_id): raise HTTPException(404, 'Gym not found')
        start, end = ist_day_bounds(first)[0], ist_day_bounds(last)[1]
        # MySQL storage uses naive UTC. All selected-date boundaries are IST.
        start, end = start.replace(tzinfo=None), end.replace(tzinfo=None)
        now = utcnow().replace(tzinfo=None)
        within = lambda col: and_(col >= start, col < end)
        gym_filter = lambda col: col == gym_id if gym_id is not None else literal(True)
        paid = paid_checkouts(self.db, mode)
        values = booking_values(self.db, mode)
        attended = attended_values(self.db, mode)
        admissions = visits(mode)
        funding_filter = self.source_filter(attended.c.provider, attended.c.gateway, attended.c.wallet, source)
        earned_query = select(attended).where(within(attended.c.event_at), gym_filter(attended.c.gym_id), funding_filter)
        attended_total = self.total(earned_query, 'total')
        wallet_attended = self.total(earned_query, 'wallet')
        selected_values = select(values.c.booking_id).where(self.source_filter(values.c.provider, values.c.gateway, values.c.wallet, source))
        selected_checkouts = select(paid.c.checkout_id).where(self.source_filter(paid.c.provider, paid.c.gateway, paid.c.wallet, source))
        # Operational pending/failed counts must not require completed funding.
        # Use the immutable chosen order source, not the successful-only projection.
        from app.services.checkout_funding import available as funding_available
        from app.models.checkout_funding import CheckoutFunding
        if source == 'WALLET':
            operational_source = exists(select(CheckoutFunding.checkout_id).where(
                CheckoutFunding.checkout_id == PaymentCheckout.id, CheckoutFunding.wallet_amount > 0)) if funding_available(self.db) else literal(False)
        elif source:
            operational_source = and_(PaymentCheckout.provider == source, PaymentCheckout.amount > 0)
        else: operational_source = literal(True)
        visit_query = select(admissions).where(within(admissions.c.event_at), gym_filter(admissions.c.gym_id))
        if source:
            visit_query = visit_query.where(or_(admissions.c.booking_id.in_(selected_values), and_(
                admissions.c.category == 'MEMBERSHIP', exists(select(Checkin.id).join(UserMembership,
                    UserMembership.id == Checkin.membership_id).where(Checkin.id == admissions.c.visit_id,
                        UserMembership.gateway_checkout_id.in_(selected_checkouts))))))
        period_visits = visit_query.subquery('period_visits')
        cohort = select(Booking.id, Booking.status, Booking.attendance_status, Booking.slot_date,
            Booking.gym_id, Booking.user_id).join(PaymentCheckout, PaymentCheckout.id == Booking.checkout_id).where(
            PaymentCheckout.mode == mode, Booking.access_source == 'BOOKING_ACCESS',
            Booking.slot_date.between(first, last), gym_filter(Booking.gym_id))
        if source: cohort = cohort.where(operational_source)
        cohort_rows = cohort.subquery('scheduled_bookings')
        valid_scan = exists(select(admissions.c.visit_id).where(admissions.c.booking_id == cohort_rows.c.id))
        cohort_counts = self.db.execute(select(func.count().label('total'),
            func.sum(case((cohort_rows.c.status == 'CONFIRMED', 1), else_=0)).label('confirmed'),
            func.sum(case((cohort_rows.c.status == 'CANCELLED', 1), else_=0)).label('cancelled'),
            func.sum(case((and_(cohort_rows.c.status == 'CONFIRMED', valid_scan), 1), else_=0)).label('attended'),
            func.sum(case((and_(cohort_rows.c.status == 'CONFIRMED', cohort_rows.c.attendance_status == 'NO_SHOW', ~valid_scan), 1), else_=0)).label('no_show'),
            func.sum(case((cohort_rows.c.status == 'PENDING_PAYMENT', 1), else_=0)).label('pending'),
            func.sum(case((cohort_rows.c.status == 'EXPIRED', 1), else_=0)).label('expired')).select_from(cohort_rows)).mappings().one()
        cohort_counts = {k: int(v or 0) for k, v in cohort_counts.items()}
        clock = ist_now()
        upcoming = select(Booking.id).join(values, values.c.booking_id == Booking.id).join(GymSlot, GymSlot.id == Booking.gym_slot_id).where(
            Booking.status == 'CONFIRMED', or_(Booking.attendance_status.is_(None), Booking.attendance_status != 'NO_SHOW'),
            Booking.slot_date.between(first, last), gym_filter(Booking.gym_id),
            or_(Booking.slot_date > clock.date(), and_(Booking.slot_date == clock.date(), GymSlot.start_time > clock.time().replace(tzinfo=None))),
            ~exists(select(Checkin.id).where(Checkin.booking_id == Booking.id, Checkin.status == 'SUCCESS')),
            self.source_filter(values.c.provider, values.c.gateway, values.c.wallet, source))
        noshow = select(values.c.total, values.c.wallet, Booking.id, Booking.attendance_marked_at.label('event_at'), Booking.gym_id).join(
            Booking, Booking.id == values.c.booking_id).where(Booking.status == 'CONFIRMED', Booking.attendance_status == 'NO_SHOW',
            within(Booking.attendance_marked_at), gym_filter(Booking.gym_id),
            ~exists(select(Checkin.id).where(Checkin.booking_id == Booking.id, Checkin.status == 'SUCCESS')),
            self.source_filter(values.c.provider, values.c.gateway, values.c.wallet, source))
        membership = select(UserMembership.id, UserMembership.membership_type, UserMembership.gym_id,
            UserMembership.created_at.label('event_at'), UserMembership.paid_amount.label('total'), paid.c.gateway,
            paid.c.wallet, UserMembership.plan_id, UserMembership.platform_plan_id).join(paid,
            paid.c.checkout_id == UserMembership.gateway_checkout_id).where(
                UserMembership.payment_status == 'PAID', UserMembership.currency == 'INR',
                UserMembership.paid_amount == paid.c.total, UserMembership.membership_type == paid.c.kind,
                paid.c.kind.in_(['SINGLE_GYM', 'MULTI_GYM']),
                or_(UserMembership.user_id == paid.c.user_id, exists(select(MembershipTransfer.id).where(
                    MembershipTransfer.membership_id == UserMembership.id, MembershipTransfer.original_user_id == paid.c.user_id,
                    MembershipTransfer.recipient_user_id == UserMembership.user_id, MembershipTransfer.status == 'COMPLETED'))),
                self.source_filter(paid.c.provider, paid.c.gateway, paid.c.wallet, source))
        if gym_id is not None:
            membership = membership.where(UserMembership.membership_type == 'SINGLE_GYM', UserMembership.gym_id == gym_id)
        membership_period = membership.where(within(UserMembership.created_at)).subquery('membership_sales')
        membership_stats = {}
        for kind in ('SINGLE_GYM', 'MULTI_GYM'):
            q = select(membership_period).where(membership_period.c.membership_type == kind)
            membership_stats[kind] = {'sales_count': self.count(q), 'sales_value': amount(self.total(q, 'total')),
                'gateway_funded_value': amount(self.total(q, 'gateway')), 'wallet_funded_value': amount(self.total(q, 'wallet')),
                'recognized_revenue': missing('Membership recognition schedule, pause treatment and principal/agent policy are not configured.')}
        # Active/expired inventory is current, not a sales event or a membership visit.
        inventory = select(UserMembership.id).where(UserMembership.id.in_(select(membership.subquery().c.id)))
        if source: inventory = inventory.where(UserMembership.gateway_checkout_id.in_(selected_checkouts))
        for kind in ('SINGLE_GYM', 'MULTI_GYM'):
            current = inventory.where(UserMembership.membership_type == kind)
            paused = exists(select(MembershipPause.id).where(MembershipPause.membership_id == UserMembership.id,
                MembershipPause.start_date <= ist_today(), MembershipPause.end_date >= ist_today()))
            current_active = current.where(UserMembership.status == 'ACTIVE', UserMembership.start_at <= now, UserMembership.end_at > now)
            membership_stats[kind]['active'] = self.count(current_active.where(~paused))
            membership_stats[kind]['paused'] = self.count(current_active.where(paused))
            membership_stats[kind]['expired'] = self.count(current.where(UserMembership.end_at <= now))
            membership_stats[kind]['expiring_30_days'] = self.count(current.where(UserMembership.status == 'ACTIVE', UserMembership.end_at > now, UserMembership.end_at <= now + timedelta(days=30)))
        transfers = select(MembershipTransfer.id).join(UserMembership, UserMembership.id == MembershipTransfer.membership_id).where(
            UserMembership.id.in_(inventory), MembershipTransfer.status == 'COMPLETED', within(MembershipTransfer.created_at))
        movements = self.wallet_report(start, end, mode, gym_id, source)
        payments = self.payment_report(start, end, mode, gym_id, source)
        wallet_purchases = select(CheckoutFunding.wallet_amount.label('amount')).join(paid,
            paid.c.checkout_id == CheckoutFunding.checkout_id).where(
                CheckoutFunding.state == 'DEBITED', within(CheckoutFunding.resolved_at),
                self.source_filter(paid.c.provider, paid.c.gateway, paid.c.wallet, source)) if funding_available(self.db) else None
        payments['wallet_funded_purchase_value'] = amount(self.total(wallet_purchases, 'amount')) if wallet_purchases is not None and gym_id is None else None
        payments['wallet_purchase_basis'] = 'Wallet debit completion date; platform-wide verified completed funding only. Not gateway collection.'
        unclassified_bookings = self.count(select(Booking.id).outerjoin(PaymentCheckout, PaymentCheckout.id == Booking.checkout_id).where(
            Booking.slot_date.between(first, last), gym_filter(Booking.gym_id),
            or_(PaymentCheckout.id.is_(None), PaymentCheckout.mode.not_in(['test', 'live']))))
        # SQL grouped events; zero-filled days, never interpolate monetary values.
        def event_day(column):
            return func.date(func.datetime(column, '+330 minutes')) if self.db.bind.dialect.name == 'sqlite' else func.date(func.date_add(column, text('INTERVAL 330 MINUTE')))
        series = {str(first + timedelta(days=n)): {'date': str(first + timedelta(days=n)), 'attended_value': '0.00', 'visits': 0, 'membership_sales_value': '0.00', 'no_show_gross': '0.00', 'wallet_credits': '0.00', 'wallet_spending': '0.00'} for n in range((last-first).days+1)}
        for query, column, key in ((earned_query, 'total', 'attended_value'), (select(membership_period), 'total', 'membership_sales_value'), (noshow, 'total', 'no_show_gross')):
            table = query.subquery()
            for day, value in self.db.execute(select(event_day(table.c.event_at), func.sum(table.c[column])).group_by(event_day(table.c.event_at))):
                if str(day) in series: series[str(day)][key] = amount(value)
        for day, count in self.db.execute(select(event_day(period_visits.c.event_at), func.count()).group_by(event_day(period_visits.c.event_at))):
            if str(day) in series: series[str(day)]['visits'] = count
        if movements['applicable']:
            for row in movements.pop('series'):
                day = str(row['day'])
                if day in series: series[day].update(wallet_credits=amount(row['credits']), wallet_spending=amount(row['spending']))
        else:
            for row in series.values(): row.update(wallet_credits=None, wallet_spending=None)
        gyms = list(self.db.execute(select(Gym.id, Gym.name, Gym.status, Gym.is_active).where(gym_filter(Gym.id)).order_by(Gym.name)).mappings())
        gym_rows = {g['id']: {**dict(g), 'visits': 0, 'attended_value': '0.00', 'single_membership_sales_value': '0.00', 'owner_payable': None, 'utilization': None} for g in gyms}
        for gid, count in self.db.execute(select(period_visits.c.gym_id, func.count()).group_by(period_visits.c.gym_id)):
            if gid in gym_rows: gym_rows[gid]['visits'] = count
        earning_rows = earned_query.subquery()
        for gid, value in self.db.execute(select(earning_rows.c.gym_id, func.sum(earning_rows.c.total)).group_by(earning_rows.c.gym_id)):
            if gid in gym_rows: gym_rows[gid]['attended_value'] = amount(value)
        for gid, value in self.db.execute(select(membership_period.c.gym_id, func.sum(membership_period.c.total)).where(
                membership_period.c.membership_type == 'SINGLE_GYM').group_by(membership_period.c.gym_id)):
            if gid in gym_rows: gym_rows[gid]['single_membership_sales_value'] = amount(value)
        people = select(period_visits.c.user_id, func.count().label('visits')).group_by(period_visits.c.user_id).subquery('customer_visits')
        active_customers = self.count(select(people))
        repeat_customers = self.count(select(people).where(people.c.visits > 1))
        customer_role = exists(select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(UserRole.user_id == User.id, Role.name == 'CUSTOMER'))
        new_customers = self.count(select(User.id).where(customer_role, within(User.created_at)))
        day_count = (last-first).days+1
        previous_visits = select(admissions.c.user_id).where(admissions.c.event_at >= start-timedelta(days=day_count), admissions.c.event_at < start, gym_filter(admissions.c.gym_id)).distinct()
        # Source-filtered retention needs the same eligible population; don't mix cohorts.
        retained = None if source else self.count(select(people.c.user_id).where(people.c.user_id.in_(previous_visits)))
        prior_count = None if source else self.count(previous_visits)
        recognized = missing('FitiGo principal/agent treatment, owner agreements and membership recognition schedules are not configured. Attended gross value below is not platform net revenue.')
        owner = missing('No effective-dated owner agreements, allocation ledger or settlement records exist. No percentage or payout is inferred.')
        return {'version': 1, 'date_from': str(first), 'date_to': str(last), 'mode': mode, 'source': source, 'gym_id': gym_id,
            'currency': 'INR', 'timezone': 'Asia/Kolkata', 'generated_at': utcnow().isoformat(),
            'options': [dict(r) for r in self.db.execute(select(Gym.id, Gym.name).order_by(Gym.name)).mappings()],
            'platform': {'total_users': self.count(select(User.id)), 'new_users': self.count(select(User.id).where(within(User.created_at))),
                'new_customers': new_customers, 'active_gyms': sum(g['status']=='APPROVED' and bool(g['is_active']) for g in gyms),
                'pending_gyms': sum(g['status']=='PENDING_APPROVAL' for g in gyms),
                'new_gyms': self.count(select(Gym.id).where(within(Gym.created_at), gym_filter(Gym.id))),
                'completed_visits': self.count(visit_query), 'upcoming_bookings': self.count(upcoming)},
            'revenue': {'attended_booking_value': amount(attended_total), 'attended_wallet_funded_value': amount(wallet_attended),
                'attended_booking_count': self.count(earned_query), 'recognized_total': recognized,
                'fitigo_booking_income': missing('Owner revenue-sharing and principal/agent policies are not configured.'),
                'no_show_count': self.count(noshow), 'no_show_gross': amount(self.total(noshow, 'total')),
                'no_show_fitigo_income': missing('No-show revenue-sharing agreement is not configured.'), 'no_show_owner_share': owner},
            'bookings': {**cohort_counts, 'upcoming': self.count(upcoming),
                'cancellation_rate': rate(cohort_counts['cancelled'], cohort_counts['total']),
                'no_show_rate': rate(cohort_counts['no_show'], cohort_counts['attended']+cohort_counts['no_show'])},
            'memberships': {'categories': membership_stats, 'transfers': self.count(transfers),
                'renewals': missing('Renewal lineage is not recorded; another purchase is not assumed to be a renewal.'),
                'plan_popularity': [dict(r, sales_value=amount(r['sales_value'])) for r in self.db.execute(select(
                    membership_period.c.membership_type, membership_period.c.plan_id, membership_period.c.platform_plan_id,
                    func.count().label('sales'), func.sum(membership_period.c.total).label('sales_value')).group_by(
                    membership_period.c.membership_type, membership_period.c.plan_id, membership_period.c.platform_plan_id)).mappings()]},
            'payments': payments, 'wallet': movements, 'settlements': {key: owner for key in (
                'total_payable', 'attended_payable', 'wallet_funded_attended_payable', 'membership_payable', 'no_show_payable',
                'paid', 'pending', 'adjustments', 'outstanding')},
            'customers': {'active': active_customers, 'repeat': repeat_customers, 'previous_active': prior_count,
                'retained': retained, 'retention_rate': rate(retained, prior_count) if prior_count is not None else None,
                'visits_per_active': rate(self.count(visit_query), active_customers) / 100 if active_customers else None,
                'membership_conversion': missing('A conversion cohort and attribution window have not been approved.'),
                'most_active': [dict(r) for r in self.db.execute(select(people).order_by(people.c.visits.desc(), people.c.user_id).limit(10)).mappings()]},
            'gyms': list(gym_rows.values()), 'series': list(series.values()),
            'data_quality': {'unclassified_mode_bookings_excluded': unclassified_bookings,
                'capture_dates': 'NOT_RECORDED', 'refund_event_dates': 'NOT_RECORDED',
                'historical_recognition_adjustments': 'Current-state evidence only; no immutable accounting journal or closed-period restatement policy.'},
            'definitions': {
                'attended': 'Full verified booking value once at the first valid QR visitor admission. Gross service value, not FitiGo net revenue. Group places do not multiply purchase value.',
                'visits': 'Unique successful visitor/daily-access admissions, validated against QR source, time window, gym and customer. Manual attendance is excluded. Membership visits do not create sales.',
                'bookings': 'Scheduled-date cohort in selected mode; no-show rate = explicitly marked no-show / (attended + no-show). No-show money uses attendance_marked_at, not scheduled date.',
                'membership_sales': 'Verified fulfilled sale once on entitlement creation date, not collection or earned-revenue date. A transfer preserves the sale. Multi-Gym sales are never assigned to each visited gym.',
                'collections': 'Actual capture and refund event dates are not stored. Undated verified provider evidence is shown separately across all dates, never assigned to first_seen_at or checkout.created_at.',
                'wallet': 'Current mode-classified wallet liability = all signed ledger movements, reconciled per account with stored balance. Holds remain liability. Period movements use wallet transaction time. Wallet liability is platform-wide, not attributable to a gym/provider.',
                'filters': 'Funding source selects whole purchases with that contribution; split purchases can occur in multiple source views, so source-view purchase totals are not additive. Global user registrations ignore gym/source/mode. Gym inventory ignores dates/payment source.',
                'unsupported': 'Unconfigured policy-dependent values are null, never zero. No historical allocation, settlement, capture date, fee or credit-consumption order is invented.'}}