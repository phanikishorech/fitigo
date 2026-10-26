"""One durable checkout per purchase; captured funds and fulfillment commit together."""
import hashlib
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.auth import User
from app.models.booking import Booking, Payment
from app.models.cart import CartItem
from app.models.class_booking import ClassSession, GymClass
from app.models.gym import Gym
from app.models.membership import UserMembership
from app.models.platform_membership import PlatformMembershipOrder
from app.models.payment_checkout import PaymentCheckout, PaymentWebhookReceipt
from app.models.slot import GymSlot
from app.services.booking_access_service import BookingAccessService, validate_visitors
from app.services.booking_time import require_future_start
from app.services.membership_entitlement import active_memberships
from app.services.membership_wallet_service import expiry, single_terms, quote_key
from app.services.payment_provider import PaymentProvider, check_order, minor
from app.services.payment_providers import get_provider, require_gateway


class PaymentCheckoutService:
    def __init__(self, db: Session):
        self.db = db
        self.gateway: PaymentProvider = get_provider()

    def bind(self, checkout):
        if self.gateway.name != checkout.provider:
            self.gateway = get_provider(checkout.provider)
        require_gateway(checkout.provider)
        if checkout.mode != settings.gateway_mode or checkout.key_id != self.gateway.key_id:
            raise HTTPException(409, detail="Checkout belongs to a different payment configuration")

    def lock_user(self, user_id):
        user = self.db.scalar(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True))
        if not user or user.status != "ACTIVE":
            raise HTTPException(403, detail="Account unavailable")
        return user

    def owned(self, checkout_id, user_id):
        self.lock_user(user_id)
        checkout = self.db.scalar(select(PaymentCheckout).where(PaymentCheckout.id == checkout_id,
            PaymentCheckout.user_id == user_id).with_for_update().execution_options(populate_existing=True))
        if not checkout:
            raise HTTPException(404, detail="Payment checkout not found")
        self.bind(checkout)
        return checkout

    def membership_eligible(self, user_id, terms):
        now = datetime.utcnow().replace(microsecond=0)
        multi = terms["membership_type"] == "MULTI_GYM"
        current = active_memberships(self.db, user_id, now, lock=True, include_paused=True)
        if any(multi or m.membership_type == "MULTI_GYM" or m.gym_id == terms.get("gym_id") for m in current):
            raise HTTPException(409, detail="Membership already active")
        if multi:
            gym = self.db.scalar(select(Gym.id).where(Gym.multi_gym_enabled.is_(True), Gym.status == "APPROVED", Gym.is_active.is_(True)).limit(1))
        else:
            gym = self.db.scalar(select(Gym.id).where(Gym.id == terms["gym_id"], Gym.status == "APPROVED", Gym.is_active.is_(True)))
        if not gym:
            raise HTTPException(409, detail="No eligible gym is available for this membership")

    def create(self, user_id: int, payload, key: str):
        require_gateway()
        customer = self.lock_user(user_id)
        kind = payload.kind
        items = []
        source = f"{kind}:{key}"
        terms = {}
        if kind == "BOOKING":
            source = f"booking:{payload.booking_id}"
        elif kind == "MULTI_GYM":
            source = f"multi:{payload.order_id}"
        elif kind == "CART":
            same_request = self.db.scalar(select(PaymentCheckout).where(PaymentCheckout.user_id == user_id,
                PaymentCheckout.source_key == f"cart-request:{key}"))
            if same_request:
                self.db.commit()
                return self.start(same_request.id, user_id)
            pending = self.db.scalar(select(PaymentCheckout).where(PaymentCheckout.user_id == user_id,
                PaymentCheckout.kind == "CART", PaymentCheckout.status.not_in(["PAID", "REFUNDED", "CANCELLED", "REVIEW_REQUIRED"])).order_by(PaymentCheckout.created_at.desc()))
            if pending:
                self.db.commit()
                return self.start(pending.id, user_id)
            items = self.db.scalars(select(CartItem).where(CartItem.user_id == user_id, CartItem.status == "ACTIVE").order_by(CartItem.id).with_for_update()).all()
            if not items:
                raise HTTPException(409, detail="Cart is empty. Check My Bookings for a completed purchase.")
            source = f"cart-request:{key}"
        previous = self.db.scalar(select(PaymentCheckout).where(PaymentCheckout.user_id == user_id, PaymentCheckout.source_key == source))
        if previous:
            if kind == "SINGLE_GYM" and (previous.snapshot.get("gym_id") != payload.gym_id or previous.snapshot.get("id") != payload.plan_id):
                raise HTTPException(409, detail="Idempotency key belongs to another purchase")
            self.db.commit()
            return self.start(previous.id, user_id)
        platform_order = None
        booking = None
        if kind == "SINGLE_GYM":
            terms = single_terms(self.db, payload.gym_id, payload.plan_id, lock=True)
        elif kind == "MULTI_GYM":
            platform_order = self.db.scalar(select(PlatformMembershipOrder).where(PlatformMembershipOrder.id == payload.order_id,
                PlatformMembershipOrder.user_id == user_id).with_for_update())
            if not platform_order or platform_order.membership_id:
                raise HTTPException(409, detail="Membership order unavailable or already fulfilled")
            from app.services.platform_membership_service import PlatformMembershipService
            terms = PlatformMembershipService(self.db).detail(platform_order.plan_id, lock=True).model_dump(mode="json")
        elif kind == "BOOKING":
            booking = self.db.scalar(select(Booking).where(Booking.id == payload.booking_id, Booking.user_id == user_id).with_for_update())
            if not booking:
                raise HTTPException(404, detail="Booking not found")
            if booking.checkout_id:
                self.db.commit()
                return self.start(booking.checkout_id, user_id)
            self.valid_booking(booking)
        if kind in {"SINGLE_GYM", "MULTI_GYM"}:
            # A new browser key/order must not charge for an overlapping pending
            # membership. Resume the same plan, block conflicting pending plans.
            for previous in self.db.scalars(select(PaymentCheckout).where(PaymentCheckout.user_id == user_id,
                PaymentCheckout.kind.in_(["SINGLE_GYM", "MULTI_GYM"]),
                PaymentCheckout.status.not_in(["PAID", "REFUNDED", "CANCELLED"]))):
                if previous.kind == kind and previous.snapshot.get("id") == terms["id"] and previous.snapshot.get("gym_id") == terms.get("gym_id"):
                    self.db.commit()
                    return self.start(previous.id, user_id)
                if kind == "MULTI_GYM" or previous.kind == "MULTI_GYM" or previous.snapshot.get("gym_id") == terms.get("gym_id"):
                    raise HTTPException(409, detail="Resolve the pending membership payment before buying another plan")
            if payload.accepted_quote != quote_key(terms):
                raise HTTPException(409, detail={"code": "MEMBERSHIP_PRICE_CHANGED"})
            self.membership_eligible(user_id, terms)
        checkout = PaymentCheckout(id=str(uuid4()), user_id=user_id, source_key=source, kind=kind,
            provider=self.gateway.name, mode=settings.gateway_mode, key_id=self.gateway.key_id,
            amount=0, currency="INR", snapshot=terms, status="CREATED")
        self.db.add(checkout)
        self.db.flush()
        if kind == "CART":
            self.prepare_cart(checkout, items)
        elif booking:
            checkout.amount, checkout.currency = booking.total_price, booking.currency
            booking.checkout_id = checkout.id
            payment = self.db.scalar(select(Payment).where(Payment.booking_id == booking.id).with_for_update())
            if not payment or payment.status == "PAID":
                raise HTTPException(409, detail="Booking payment unavailable")
            payment.provider = checkout.provider
        else:
            checkout.amount, checkout.currency = Decimal(terms["final_price"]), terms["currency"]
            if platform_order:
                platform_order.checkout_id = checkout.id
                platform_order.snapshot = terms
        if checkout.currency != "INR" or minor(checkout.amount) < 0:
            raise HTTPException(409, detail="This checkout supports INR only")
        self.gateway.validate_purchase(checkout, customer)
        self.db.commit()
        return self.start(checkout.id, user_id)

    def prepare_cart(self, checkout, items):
        from app.routers.cart import _operating_hours_for_date, _validate_checkout_times
        _validate_checkout_times(self.db, items)
        total = Decimal("0")
        for item in items:
            gym = self.db.get(Gym, item.gym_id)
            if not gym or gym.status != "APPROVED" or not gym.is_active:
                raise HTTPException(409, detail="Gym unavailable")
            if item.currency != "INR":
                raise HTTPException(409, detail="Cart currency mismatch")
            if item.booking_type == "GYM":
                opening, closing, closed = _operating_hours_for_date(self.db, gym_id=gym.id, dt=item.booking_date)
                if closed or not opening or not closing or item.preferred_start_time < opening or item.preferred_end_time > closing:
                    raise HTTPException(409, detail="Gym visit is outside operating hours")
                start, end, name, price, capacity = item.preferred_start_time, item.preferred_end_time, "Gym Access", Decimal(str(gym.gym_price_per_person)), 500
            else:
                session = self.db.scalar(select(ClassSession).where(ClassSession.id == item.class_session_id).with_for_update())
                gclass = self.db.get(GymClass, session.gym_class_id) if session else None
                if not session or not gclass or not gclass.is_active or gclass.gym_id != gym.id or session.status not in {"AVAILABLE", "FEW_SLOTS_LEFT"}:
                    raise HTTPException(409, detail="Class unavailable")
                if session.maximum_capacity - session.booked_capacity < item.member_count:
                    raise HTTPException(409, detail="Class capacity unavailable")
                start, end, name, price, capacity = session.start_time, session.end_time, gclass.class_name, Decimal(str(session.price_per_person)), session.maximum_capacity
            if Decimal(str(item.price_per_person)) != price:
                raise HTTPException(409, detail="Booking price changed. Remove the item and add it again to review the new price.")
            names = validate_visitors(item.visitor_names, item.member_count)
            slot = self.db.scalar(select(GymSlot).where(GymSlot.gym_id == gym.id, GymSlot.start_time == start, GymSlot.end_time == end, GymSlot.name == name, GymSlot.is_active == 1))
            if not slot:
                slot = GymSlot(gym_id=gym.id, name=name, start_time=start, end_time=end, capacity=capacity, price=price, is_active=1)
                self.db.add(slot); self.db.flush()
            amount = price * item.member_count
            notes = f"access_type_id={'GROUP_CLASS' if item.booking_type == 'CLASS' else 'GYM_WORKOUT'}\ncart_item_id={item.id}"
            if item.class_session_id:
                notes += f"\nclass_session_id={item.class_session_id}"
            booking = Booking(user_id=checkout.user_id, gym_id=gym.id, gym_slot_id=slot.id, slot_date=item.booking_date,
                quantity=item.member_count, visitor_names=names, unit_price=price, total_price=amount, currency="INR",
                status="PENDING_PAYMENT", expires_at=datetime.utcnow() + timedelta(minutes=15), notes=notes,
                idempotency_key=f"cart:{item.id}", checkout_id=checkout.id, access_source="BOOKING_ACCESS")
            self.db.add(booking); self.db.flush()
            self.db.add(Payment(booking_id=booking.id, provider=checkout.provider, status="INITIATED", amount=amount, currency="INR"))
            item.status, item.checkout_id = "PAYMENT_PENDING", checkout.id
            total += amount
        checkout.amount = total
        checkout.snapshot = {"cart_item_ids": [item.id for item in items]}

    def valid_booking(self, booking):
        if booking.status != "PENDING_PAYMENT" or booking.expires_at < datetime.utcnow():
            raise HTTPException(409, detail="Booking cancelled, expired or no longer pending")
        slot, gym = self.db.get(GymSlot, booking.gym_slot_id), self.db.get(Gym, booking.gym_id)
        if not slot or not gym or gym.status != "APPROVED" or not gym.is_active:
            raise HTTPException(409, detail="Booking is unavailable")
        require_future_start(booking.slot_date, slot.start_time)

    def check_order(self, checkout, order):
        check_order(checkout, order)
        checkout.checkout_data = {**order.checkout_data, "payable": order.payable}

    def start(self, checkout_id, user_id):
        checkout = self.owned(checkout_id, user_id)
        if checkout.status == "CREATED":
            if minor(checkout.amount) == 0:
                self.fulfill(checkout, None)
                self.db.commit()
                return self.present(checkout)
            # Commit intent BEFORE external side effect. Unknown outcomes are
            # reconciled by receipt; never blindly create another gateway order.
            checkout.status = "CREATING"
            self.db.commit()
            order = self.gateway.create_order(checkout, self.db.get(User, user_id))
            checkout = self.owned(checkout_id, user_id)
            self.check_order(checkout, order)
            checkout.gateway_order_id = order.id
            if checkout.status == "CREATING":
                checkout.status = "PENDING"
            self.db.commit()
            return self.present(checkout)
        return self.reconcile(checkout_id, user_id)

    def reconcile(self, checkout_id, user_id, payment_id=None, signature=None, order_id=None, commit=True):
        checkout = self.owned(checkout_id, user_id)
        self.gateway.verify_confirmation(checkout, payment_id, signature, order_id)
        if checkout.status == "CREATING" and not checkout.gateway_order_id:
            order = self.gateway.find_order(checkout.id)
            if order:
                self.check_order(checkout, order)
                checkout.gateway_order_id, checkout.status = order.id, "PENDING"
        if checkout.gateway_order_id:
            order = self.gateway.order(checkout.gateway_order_id)
            self.check_order(checkout, order)
            payments = self.gateway.payments(checkout.gateway_order_id, payment_id)
            verified = []
            for payment in payments:
                if payment.order_id != checkout.gateway_order_id or payment.amount != minor(checkout.amount) or payment.currency != checkout.currency:
                    raise HTTPException(409, detail="Payment amount, currency or ownership mismatch")
                verified.append(payment)
            captured = next((p for p in verified if p.status == "SUCCESS" and not p.refunded), None)
            refunded = next((p for p in verified if (not checkout.gateway_payment_id or p.id == checkout.gateway_payment_id)
                and p.refunded > 0), None)
            if refunded:
                checkout.gateway_payment_id = refunded.id
                self.revoke(checkout, full=refunded.refunded == minor(checkout.amount))
            elif captured and checkout.status not in {"PAID", "REVIEW_REQUIRED", "REFUNDED"}:
                if not order.paid:
                    raise HTTPException(409, detail="Order is not fully paid")
                checkout.gateway_payment_id = captured.id
                try:
                    # Roll back all partial booking/class/QR/membership writes if
                    # access eligibility changed while the payment was in flight.
                    with self.db.begin_nested():
                        self.fulfill(checkout, captured.id)
                except HTTPException:
                    checkout.status, checkout.failure_code = "REVIEW_REQUIRED", "FULFILLMENT_UNAVAILABLE"
                    self.record_paid(checkout, captured.id)
            elif checkout.status not in {"PAID", "REVIEW_REQUIRED", "REFUNDED", "CANCELLED"}:
                checkout.status = "PENDING" if any(p.status == "PENDING" for p in verified) else "FAILED" if verified or not order.payable else "PENDING"
                for payment in self.db.scalars(select(Payment).join(Booking, Booking.id == Payment.booking_id)
                    .where(Booking.checkout_id == checkout.id, Booking.status == "PENDING_PAYMENT")):
                    if payment.status != "PAID":
                        payment.status = "FAILED" if checkout.status == "FAILED" else "INITIATED"
        if commit:
            self.db.commit()
        return self.present(checkout)

    def record_paid(self, checkout, payment_id):
        for payment in self.db.scalars(select(Payment).join(Booking, Booking.id == Payment.booking_id).where(Booking.checkout_id == checkout.id)):
            payment.status, payment.provider, payment.external_ref = "PAID", checkout.provider if payment_id else "FREE", payment_id

    def fulfill(self, checkout, payment_id):
        if checkout.status == "PAID":
            return
        if checkout.status == "CANCELLED":
            raise HTTPException(409, detail="Checkout was cancelled")
        if checkout.kind in {"SINGLE_GYM", "MULTI_GYM"}:
            self.membership_eligible(checkout.user_id, checkout.snapshot)
            terms, now = checkout.snapshot, datetime.utcnow().replace(microsecond=0)
            multi = terms["membership_type"] == "MULTI_GYM"
            end = expiry(now, terms["duration_value"], terms["duration_unit"])
            membership = UserMembership(user_id=checkout.user_id, gym_id=None if multi else terms["gym_id"],
                plan_id=None if multi else terms["id"], platform_plan_id=terms["id"] if multi else None,
                membership_type=terms["membership_type"], checkout_key=f"{checkout.provider.lower()}:{checkout.id}", gateway_checkout_id=checkout.id,
                terms_snapshot=terms, status="ACTIVE", start_at=now, end_at=end, original_end_at=end,
                paid_amount=checkout.amount, currency=checkout.currency, payment_provider=checkout.provider if payment_id else "FREE",
                payment_status="PAID", external_ref=payment_id)
            self.db.add(membership); self.db.flush()
            if checkout.kind == "MULTI_GYM":
                order = self.db.scalar(select(PlatformMembershipOrder).where(PlatformMembershipOrder.checkout_id == checkout.id).with_for_update())
                order.membership_id, order.status = membership.id, "PAID"
        else:
            bookings = self.db.scalars(select(Booking).where(Booking.checkout_id == checkout.id).order_by(Booking.id).with_for_update().execution_options(populate_existing=True)).all()
            if not bookings or sum(Decimal(str(b.total_price)) for b in bookings) != checkout.amount:
                raise HTTPException(409, detail="Booking totals changed")
            for booking in bookings:
                self.valid_booking(booking)
                # Cart sources are server-linked records. Customer-supplied
                # booking notes must never decide which class capacity to debit.
                item = None
                if checkout.kind == "CART":
                    item = self.db.scalar(select(CartItem).where(CartItem.checkout_id == checkout.id,
                        CartItem.id == int(booking.idempotency_key.removeprefix("cart:"))))
                    if not item:
                        raise HTTPException(409, detail="Cart source unavailable")
                if item and item.class_session_id:
                    session = self.db.scalar(select(ClassSession).where(ClassSession.id == item.class_session_id).with_for_update())
                    if not session or session.status not in {"AVAILABLE", "FEW_SLOTS_LEFT"} or session.maximum_capacity - session.booked_capacity < booking.quantity:
                        raise HTTPException(409, detail="Class capacity unavailable")
                    session.booked_capacity += booking.quantity
                booking.status = "CONFIRMED"
            self.record_paid(checkout, payment_id)
            self.db.flush()
            for booking in bookings:
                BookingAccessService(self.db).ensure_records(booking)
            for item in self.db.scalars(select(CartItem).where(CartItem.checkout_id == checkout.id).with_for_update()):
                item.status = "CONFIRMED"
        checkout.status, checkout.failure_code = "PAID", None

    def revoke(self, checkout, full=True):
        checkout.status = "REFUNDED" if full else "REVIEW_REQUIRED"
        checkout.failure_code = None if full else "PARTIAL_REFUND"
        for booking in self.db.scalars(select(Booking).where(Booking.checkout_id == checkout.id).with_for_update()):
            booking.status = "CANCELLED"
            BookingAccessService(self.db).revoke(booking)
            payment = self.db.scalar(select(Payment).where(Payment.booking_id == booking.id))
            payment.status = "REFUNDED" if full else "PARTIALLY_REFUNDED"
        for membership in self.db.scalars(select(UserMembership).where(UserMembership.gateway_checkout_id == checkout.id).with_for_update()):
            membership.status, membership.payment_status = "CANCELLED", "REFUNDED" if full else "PARTIALLY_REFUNDED"

    def present(self, checkout):
        bookings = list(self.db.scalars(select(Booking.id).where(Booking.checkout_id == checkout.id)))
        membership = self.db.scalar(select(UserMembership.id).where(UserMembership.gateway_checkout_id == checkout.id))
        can_pay = checkout.status in {"PENDING", "FAILED"} and bool(checkout.gateway_order_id) and (checkout.checkout_data or {}).get("payable", True)
        if can_pay and bookings:
            can_pay = all(b.status == "PENDING_PAYMENT" and b.expires_at > datetime.utcnow() for b in self.db.scalars(select(Booking).where(Booking.checkout_id == checkout.id)))
        return {"id": checkout.id, "kind": checkout.kind, "status": checkout.status, "mode": checkout.mode, "amount": str(checkout.amount),
            "amount_minor": minor(checkout.amount), "currency": checkout.currency, "provider": checkout.provider,
            "environment": "sandbox" if checkout.mode == "test" else "production",
            "gateway_order_id": checkout.gateway_order_id, "booking_ids": bookings, "membership_id": membership,
            **get_provider(checkout.provider).checkout_info(checkout),
            "can_pay": can_pay, "failure_code": checkout.failure_code}

    def cancel(self, checkout_id, user_id):
        self.reconcile(checkout_id, user_id)
        checkout = self.owned(checkout_id, user_id)
        if checkout.status in {"PAID", "REVIEW_REQUIRED", "REFUNDED"}:
            return self.present(checkout)
        checkout.status = "CANCELLED"
        for booking in self.db.scalars(select(Booking).where(Booking.checkout_id == checkout.id).with_for_update()):
            if booking.status == "PENDING_PAYMENT":
                # Cart checkout does not reserve slot capacity before capture.
                if checkout.kind == "BOOKING":
                    from app.models.slot import SlotAvailability
                    av = self.db.scalar(select(SlotAvailability).where(SlotAvailability.gym_slot_id == booking.gym_slot_id,
                        SlotAvailability.slot_date == booking.slot_date).with_for_update())
                    if av:
                        av.booked_count = max(0, av.booked_count - booking.quantity)
                        if av.status == "FULL":
                            av.status = "AVAILABLE"
                booking.status, booking.cancelled_at = "CANCELLED", datetime.utcnow()
                BookingAccessService(self.db).revoke(booking)
        for item in self.db.scalars(select(CartItem).where(CartItem.checkout_id == checkout.id)):
            item.status = "REMOVED"
        self.db.commit()
        return self.present(checkout)

    def webhook(self, raw: bytes, signature: str, event_id: str = "", provider="RAZORPAY", timestamp=""):
        require_gateway(provider)
        self.gateway = get_provider(provider)
        event = self.gateway.webhook(raw, signature, timestamp)
        if event is None:
            return {"status": "ignored"}
        checkout = self.db.scalar(select(PaymentCheckout).where(
            PaymentCheckout.provider == provider, PaymentCheckout.gateway_order_id == event.order_id))
        if not checkout:
            # Recover the deterministic internal reference if create response was lost.
            receipt = event.reference or self.gateway.order(event.order_id).reference
            checkout = self.db.get(PaymentCheckout, receipt) if receipt else None
        if not checkout or checkout.provider != provider:
            return {"status": "ignored"}
        checkout = self.owned(checkout.id, checkout.user_id)
        digest = hashlib.sha256(raw).hexdigest()
        # Cashfree event headers vary by webhook version. Signed-body identity is
        # stable across retries; business fulfillment is independently idempotent.
        receipt_id = event_id if provider == "RAZORPAY" else f"cashfree:{digest}"
        previous = self.db.get(PaymentWebhookReceipt, receipt_id)
        if previous:
            if previous.body_hash != digest:
                raise HTTPException(409, detail="Webhook event ID conflict")
            if checkout.status in {"CREATING", "PENDING", "FAILED"}:
                self.reconcile(checkout.id, checkout.user_id)
            return {"status": "duplicate"}
        if not checkout.gateway_order_id:
            order = self.gateway.order(event.order_id)
            self.check_order(checkout, order)
            checkout.gateway_order_id = event.order_id
            if checkout.status == "CREATING":
                checkout.status = "PENDING"
        self.db.flush()
        self.reconcile(checkout.id, checkout.user_id, commit=False)
        self.db.add(PaymentWebhookReceipt(id=receipt_id, body_hash=digest, event=event.name))
        self.db.commit()
        return {"status": "processed"}