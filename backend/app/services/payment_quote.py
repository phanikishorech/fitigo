"""Read-only source validation and pricing for the existing checkout types."""
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from app.models.booking import Booking
from app.models.cart import CartItem
from app.models.platform_membership import PlatformMembershipOrder
from app.services.membership_wallet_service import single_terms, quote_key
from app.services.checkout_funding import calculate


def quote(service, user_id, payload):
    from app.services.platform_membership_service import PlatformMembershipService
    if payload.kind == 'WALLET_TOPUP': raise HTTPException(400, 'Wallet recharge uses gateway payment only.')
    service.lock_user(user_id)
    if payload.kind == 'BOOKING':
        booking = service.db.scalar(select(Booking).where(Booking.id == payload.booking_id, Booking.user_id == user_id))
        if not booking: raise HTTPException(404, 'Booking not found')
        if booking.checkout_id: raise HTTPException(409, 'Resume the existing checkout to review its fixed amounts.')
        service.valid_booking(booking)
        amount, currency = booking.total_price, booking.currency
    elif payload.kind == 'SINGLE_GYM':
        terms = single_terms(service.db, payload.gym_id, payload.plan_id)
        if quote_key(terms) != payload.accepted_quote: raise HTTPException(409, 'Membership price changed. Review the plan again.')
        service.membership_eligible(user_id, terms)
        amount, currency = terms['final_price'], terms['currency']
    elif payload.kind == 'MULTI_GYM':
        order = service.db.scalar(select(PlatformMembershipOrder).where(PlatformMembershipOrder.id == payload.order_id, PlatformMembershipOrder.user_id == user_id))
        if not order: raise HTTPException(404, 'Membership order not found')
        if order.checkout_id:
            from app.models.payment_checkout import PaymentCheckout
            previous = service.db.get(PaymentCheckout, order.checkout_id)
            if not previous or not service.safely_closed(previous):
                raise HTTPException(409, 'Resume the existing checkout to review its fixed amounts.')
        terms = PlatformMembershipService(service.db).detail(order.plan_id).model_dump(mode="json")
        if quote_key(terms) != payload.accepted_quote: raise HTTPException(409, 'Membership price changed. Review the plan again.')
        service.membership_eligible(user_id, terms)
        amount, currency = terms['final_price'], terms['currency']
    else:
        items = list(service.db.scalars(select(CartItem).where(CartItem.user_id == user_id, CartItem.status == 'ACTIVE').order_by(CartItem.id)))
        if not items or (payload.cart_item_ids is not None and set(payload.cart_item_ids) != {i.id for i in items}):
            raise HTTPException(409, 'Your cart changed. Reload it before paying.')
        from app.routers.cart import _validate_checkout_times
        _validate_checkout_times(service.db, items)
        amount = sum((service.cart_item_terms(item)[4] * item.member_count for item in items), Decimal(0))
        currency = 'INR'

    if currency != 'INR': raise HTTPException(409, 'This checkout supports INR only.')
    return calculate(service.db, user_id, amount, payload)