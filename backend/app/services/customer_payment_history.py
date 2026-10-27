"""Customer gateway payments only; wallet spending stays in the wallet ledger."""
from sqlalchemy import cast, func, literal, select, String, union_all
from app.core.time import as_ist
from app.models.booking import Booking, Payment
from app.models.membership import UserMembership
from app.models.payment_checkout import PaymentCheckout, PaymentAttempt
from app.models.wallet import WalletTransaction
from app.models.platform_membership import PlatformMembershipOrder


def history(db, user_id, limit, offset, status=None, kind=None):
    # One gateway checkout row for an entire cart; booking allocations appear as
    # details rather than double-counted purchases.
    queries = [select(PaymentCheckout.id.label('id'), literal('checkout').label('source'),
        PaymentCheckout.kind.label('kind'), PaymentCheckout.status.label('status'), PaymentCheckout.created_at.label('created_at'))
        .where(PaymentCheckout.user_id == user_id, PaymentCheckout.provider.in_(['RAZORPAY', 'CASHFREE']), PaymentCheckout.amount > 0)]
    queries.append(select(cast(Payment.id, String).label('id'), literal('booking').label('source'), literal('BOOKING').label('kind'),
        Payment.status.label('status'), Payment.created_at.label('created_at')).join(Booking, Booking.id == Payment.booking_id)
        .where(Booking.user_id == user_id, Booking.checkout_id.is_(None), Payment.provider.in_(['RAZORPAY', 'CASHFREE']), Payment.amount > 0))
    queries.append(select(cast(UserMembership.id, String).label('id'), literal('membership').label('source'),
        UserMembership.membership_type.label('kind'), UserMembership.payment_status.label('status'), UserMembership.created_at.label('created_at'))
        .where(UserMembership.user_id == user_id, UserMembership.gateway_checkout_id.is_(None),
               UserMembership.payment_provider.in_(['RAZORPAY', 'CASHFREE']), UserMembership.paid_amount > 0))
    rows = union_all(*queries).subquery()
    query = select(rows)
    if status:
        query = query.where(rows.c.status == status)
    if kind:
        query = query.where(rows.c.kind == kind)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    page = db.execute(query.order_by(rows.c.created_at.desc(), rows.c.source, rows.c.id.desc()).limit(limit).offset(offset)).mappings()
    items = []
    for row in page:
        item = dict(row)
        item['id'] = f"{row['source']}:{row['id']}"
        item['created_at'] = as_ist(row['created_at']).isoformat()
        item.update(attempts=[], bookings=[], membership_ids=[], wallet_entries=[], provider_order_id=None,
                    transaction_id=None, checkout_id=None, mode=None, order_details=None, failure_code=None)
        if row['source'] == 'checkout':
            purchase = db.get(PaymentCheckout, row['id'])
            item.update(checkout_id=purchase.id, amount=str(purchase.amount), currency=purchase.currency,
                provider=purchase.provider, mode=purchase.mode, provider_order_id=purchase.gateway_order_id,
                transaction_id=purchase.gateway_payment_id, failure_code=purchase.failure_code,
                updated_at=as_ist(purchase.updated_at).isoformat())
            item['attempts'] = [dict(transaction_id=p.external_id, status=p.status, amount=str(p.amount),
                currency=p.currency, refunded_amount=str(p.refunded_amount), first_seen_at=as_ist(p.first_seen_at).isoformat(),
                updated_at=as_ist(p.updated_at).isoformat()) for p in db.scalars(select(PaymentAttempt)
                    .where(PaymentAttempt.checkout_id == purchase.id).order_by(PaymentAttempt.first_seen_at, PaymentAttempt.id))]
            item['bookings'] = [dict(id=b.id, gym_id=b.gym_id, date=str(b.slot_date), status=b.status,
                quantity=b.quantity, amount=str(b.total_price), currency=b.currency) for b in db.scalars(select(Booking)
                    .where(Booking.checkout_id == purchase.id, Booking.user_id == user_id))]
            item['membership_ids'] = list(db.scalars(select(UserMembership.id).where(UserMembership.gateway_checkout_id == purchase.id, UserMembership.user_id == user_id)))
            order = db.scalar(select(PlatformMembershipOrder.id).where(PlatformMembershipOrder.checkout_id == purchase.id, PlatformMembershipOrder.user_id == user_id))
            item['order_details'] = {key: purchase.snapshot.get(key) for key in ('name', 'gym_id', 'duration_value', 'duration_unit', 'final_price', 'requested_amount') if key in purchase.snapshot}
            item['order_details']['membership_order_id'] = order
            item['wallet_entries'] = [dict(id=w.id, direction=w.direction, type=w.txn_type, amount=str(w.amount)) for w in db.scalars(select(WalletTransaction).where(WalletTransaction.checkout_id == purchase.id, WalletTransaction.user_id == user_id))]
        elif row['source'] == 'booking':
            p = db.get(Payment, int(row['id']))
            item.update(amount=str(p.amount), currency=p.currency, provider=p.provider, transaction_id=p.external_ref,
                bookings=[{'id': p.booking_id}])
        elif row['source'] == 'membership':
            m = db.get(UserMembership, int(row['id']))
            item.update(amount=str(m.paid_amount), currency=m.currency, provider=m.payment_provider,
                transaction_id=m.external_ref, membership_ids=[m.id], order_details={'name': (m.terms_snapshot or {}).get('name')})
        items.append(item)
    return {'items': items, 'total': int(total)}