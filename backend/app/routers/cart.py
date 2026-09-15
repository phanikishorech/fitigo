from __future__ import annotations

from datetime import date as date_t, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_optional_user
from app.database.session import get_db
from app.models.auth import User
from app.models.cart import BookingType, CartItem, CartItemStatus
from app.models.class_booking import ClassSession, ClassSessionStatus, GymClass, GymSpecialHours
from app.models.gym import Gym, GymOperatingHours
from app.schemas.cart import (
    CartCheckoutResponse,
    CartItemCreateClassRequest,
    CartItemCreateGymRequest,
    CartItemResponse,
    CartWalletCheckoutResponse,
)
from app.models.wallet import WalletAccount, WalletTransaction, WalletTxnDirection, WalletTxnType
from app.models.booking import Booking, BookingStatus, Payment, PaymentStatus
from app.models.slot import GymSlot


router = APIRouter(prefix="/cart")


def _operating_hours_for_date(db: Session, *, gym_id: int, dt: date_t):
    sp = (
        db.execute(select(GymSpecialHours).where(GymSpecialHours.gym_id == gym_id, GymSpecialHours.date == dt))
        .scalars()
        .first()
    )
    if sp:
        return sp.open_time, sp.close_time, bool(sp.is_closed)

    dow = dt.weekday()
    row = (
        db.execute(select(GymOperatingHours).where(GymOperatingHours.gym_id == gym_id, GymOperatingHours.day_of_week == dow))
        .scalars()
        .first()
    )
    if not row:
        return None, None, True
    return row.open_time, row.close_time, bool(row.is_closed)


def _get_dev_customer_id(db: Session) -> int | None:
    # Keep behavior consistent with gyms_public.py dev flows.
    u = db.execute(select(User).where(User.email == "customer@example.com")).scalars().first()
    return int(u.id) if u else None


def _require_user_id(db: Session, current_user: User | None) -> int:
    uid = int(current_user.id) if current_user else _get_dev_customer_id(db)
    if uid is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return uid


def _to_cart_item_response(
    *,
    item: CartItem,
    gym_name: str | None = None,
    class_name: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    available_capacity: int | None = None,
) -> CartItemResponse:
    return CartItemResponse(
        id=int(item.id),
        booking_type=item.booking_type,
        gym_id=int(item.gym_id),
        class_session_id=int(item.class_session_id) if item.class_session_id is not None else None,
        booking_date=item.booking_date,
        preferred_start_time=item.preferred_start_time,
        preferred_end_time=item.preferred_end_time,
        member_count=int(item.member_count),
        price_per_person=str(Decimal(str(item.price_per_person)).quantize(Decimal("0.01"))),
        total_price=str(Decimal(str(item.total_price)).quantize(Decimal("0.01"))),
        currency=item.currency,
        status=item.status,
        gym_name=gym_name,
        class_name=class_name,
        start_time=start_time,
        end_time=end_time,
        available_capacity=available_capacity,
    )


@router.get("/items", response_model=list[CartItemResponse])
def list_cart_items(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    uid = _require_user_id(db, current_user)
    items = (
        db.execute(
            select(CartItem)
            .where(CartItem.user_id == uid, CartItem.status == CartItemStatus.ACTIVE.value)
            .order_by(CartItem.id.desc())
        )
        .scalars()
        .all()
    )

    # Enrich with gym + class names (best-effort)
    gym_ids = {int(i.gym_id) for i in items}
    gym_map = {}
    if gym_ids:
        gym_map = {int(g.id): g.name for g in db.execute(select(Gym).where(Gym.id.in_(gym_ids))).scalars().all()}

    out: list[CartItemResponse] = []
    for it in items:
        if it.booking_type == BookingType.CLASS.value and it.class_session_id is not None:
            row = (
                db.execute(
                    select(ClassSession, GymClass)
                    .join(GymClass, GymClass.id == ClassSession.gym_class_id)
                    .where(ClassSession.id == it.class_session_id)
                )
                .first()
            )
            if row:
                sess, gclass = row
                max_cap = int(sess.maximum_capacity or 0)
                booked = int(sess.booked_capacity or 0)
                available = max(0, max_cap - booked)
                out.append(
                    _to_cart_item_response(
                        item=it,
                        gym_name=gym_map.get(int(it.gym_id)),
                        class_name=gclass.class_name,
                        start_time=str(sess.start_time),
                        end_time=str(sess.end_time),
                        available_capacity=available,
                    )
                )
                continue

        out.append(_to_cart_item_response(item=it, gym_name=gym_map.get(int(it.gym_id))))
    return out


@router.delete("/items/{item_id}", response_model=dict)
def remove_cart_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    uid = _require_user_id(db, current_user)
    it = db.execute(select(CartItem).where(CartItem.id == item_id, CartItem.user_id == uid)).scalars().first()
    if not it:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")
    it.status = CartItemStatus.REMOVED.value
    it.updated_at = datetime.utcnow()
    db.commit()
    return {"status": "ok"}


@router.post("/items/gym", response_model=CartItemResponse)
def add_gym_to_cart(
    payload: CartItemCreateGymRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    uid = _require_user_id(db, current_user)
    if payload.booking_type != BookingType.GYM.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="booking_type must be GYM")

    gym = db.execute(select(Gym).where(Gym.id == payload.gym_id, Gym.status == "APPROVED", Gym.is_active.is_(True))).scalars().first()
    if not gym:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

    # Validate times
    if payload.preferred_end_time <= payload.preferred_start_time:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="End time must be after start time")

    open_time, close_time, is_closed = _operating_hours_for_date(db, gym_id=int(gym.id), dt=payload.booking_date)
    if is_closed or not open_time or not close_time:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Gym is closed on the selected date")
    if payload.preferred_start_time < open_time or payload.preferred_start_time > close_time:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Preferred start time must be within opening hours")
    if payload.preferred_end_time > close_time or payload.preferred_end_time < open_time:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Preferred end time must be within opening hours")

    price = Decimal(str(getattr(gym, "gym_price_per_person", 0) or 0)).quantize(Decimal("0.01"))
    total = (price * Decimal(int(payload.member_count))).quantize(Decimal("0.01"))

    # Dedupe: if the exact same gym/date/time range exists in cart, update it instead of inserting a new row.
    existing = (
        db.execute(
            select(CartItem)
            .where(
                CartItem.user_id == uid,
                CartItem.status == CartItemStatus.ACTIVE.value,
                CartItem.booking_type == BookingType.GYM.value,
                CartItem.gym_id == int(payload.gym_id),
                CartItem.booking_date == payload.booking_date,
                CartItem.preferred_start_time == payload.preferred_start_time,
                CartItem.preferred_end_time == payload.preferred_end_time,
            )
            .limit(1)
        )
        .scalars()
        .first()
    )
    if existing:
        existing.member_count = int(payload.member_count)
        existing.price_per_person = float(price)
        existing.total_price = float(total)
        db.commit()
        db.refresh(existing)
        return _to_cart_item_response(item=existing, gym_name=gym.name)

    it = CartItem(
        user_id=uid,
        booking_type=BookingType.GYM.value,
        gym_id=int(payload.gym_id),
        class_session_id=None,
        booking_date=payload.booking_date,
        preferred_start_time=payload.preferred_start_time,
        preferred_end_time=payload.preferred_end_time,
        member_count=int(payload.member_count),
        price_per_person=float(price),
        total_price=float(total),
        currency="INR",
        status=CartItemStatus.ACTIVE.value,
    )
    db.add(it)
    db.commit()
    db.refresh(it)
    return _to_cart_item_response(item=it, gym_name=gym.name)


@router.post("/items/class", response_model=CartItemResponse)
def add_class_to_cart(
    payload: CartItemCreateClassRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    uid = _require_user_id(db, current_user)
    if payload.booking_type != BookingType.CLASS.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="booking_type must be CLASS")

    gym = db.execute(select(Gym).where(Gym.id == payload.gym_id, Gym.status == "APPROVED", Gym.is_active.is_(True))).scalars().first()
    if not gym:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")
    if not bool(getattr(gym, "has_classes", False)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Classes are not available at this gym.")

    # Load session + class to validate ownership.
    row = (
        db.execute(
            select(ClassSession, GymClass)
            .join(GymClass, GymClass.id == ClassSession.gym_class_id)
            .where(ClassSession.id == payload.class_session_id)
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class session not found")
    sess, gclass = row
    if int(gclass.gym_id) != int(gym.id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Class does not belong to this gym")
    if not bool(gclass.is_active):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Class is inactive")

    # Date must match
    if sess.session_date != payload.booking_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected date does not match class session")

    if sess.status in {ClassSessionStatus.CANCELLED.value, ClassSessionStatus.CLOSED.value}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Class session is not bookable")

    max_cap = int(sess.maximum_capacity or 0)
    booked = int(sess.booked_capacity or 0)
    available = max(0, max_cap - booked)
    if available <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Class is full")
    if available < int(payload.member_count):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {available} slots are available for this class.",
        )

    price = Decimal(str(sess.price_per_person or 0)).quantize(Decimal("0.01"))
    total = (price * Decimal(int(payload.member_count))).quantize(Decimal("0.01"))

    # Dedupe: if same class_session is already in cart, update member_count instead of inserting.
    existing = (
        db.execute(
            select(CartItem)
            .where(
                CartItem.user_id == uid,
                CartItem.status == CartItemStatus.ACTIVE.value,
                CartItem.booking_type == BookingType.CLASS.value,
                CartItem.gym_id == int(payload.gym_id),
                CartItem.class_session_id == int(payload.class_session_id),
                CartItem.booking_date == payload.booking_date,
            )
            .limit(1)
        )
        .scalars()
        .first()
    )
    if existing:
        existing.member_count = int(payload.member_count)
        existing.price_per_person = float(price)
        existing.total_price = float(total)
        db.commit()
        db.refresh(existing)
        return _to_cart_item_response(
            item=existing,
            gym_name=gym.name,
            class_name=gclass.class_name,
            start_time=str(sess.start_time),
            end_time=str(sess.end_time),
            available_capacity=available,
        )

    it = CartItem(
        user_id=uid,
        booking_type=BookingType.CLASS.value,
        gym_id=int(payload.gym_id),
        class_session_id=int(payload.class_session_id),
        booking_date=payload.booking_date,
        preferred_start_time=None,
        preferred_end_time=None,
        member_count=int(payload.member_count),
        price_per_person=float(price),
        total_price=float(total),
        currency="INR",
        status=CartItemStatus.ACTIVE.value,
    )
    db.add(it)
    db.commit()
    db.refresh(it)

    return _to_cart_item_response(
        item=it,
        gym_name=gym.name,
        class_name=gclass.class_name,
        start_time=str(sess.start_time),
        end_time=str(sess.end_time),
        available_capacity=available,
    )


@router.post("/checkout", response_model=CartCheckoutResponse)
def checkout_cart(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    """Confirm all ACTIVE cart items.

    MVP semantics:
    - Marks cart items as CONFIRMED
    - For CLASS items, increments ClassSession.booked_capacity (capacity reservation)
    - For GYM items, only re-validates opening hours/time range

    This provides a usable "Proceed to Book" step without implementing full payments/wallet.
    """

    uid = _require_user_id(db, current_user)

    items = (
        db.execute(
            select(CartItem)
            .where(CartItem.user_id == uid, CartItem.status == CartItemStatus.ACTIVE.value)
            .order_by(CartItem.id.asc())
            .with_for_update()
        )
        .scalars()
        .all()
    )
    if not items:
        return CartCheckoutResponse(confirmed_items=[], total_amount="0.00", currency="INR")

    confirmed: list[CartItemResponse] = []
    total = Decimal("0.00")

    # Preload gyms names
    gym_ids = sorted({int(i.gym_id) for i in items})
    gym_map: dict[int, str] = {}
    if gym_ids:
        gyms = db.execute(select(Gym).where(Gym.id.in_(gym_ids))).scalars().all()
        gym_map = {int(g.id): g.name for g in gyms}

    try:
        for it in items:
            if it.booking_type == BookingType.GYM.value:
                # Re-validate operating hours
                open_time, close_time, is_closed = _operating_hours_for_date(db, gym_id=int(it.gym_id), dt=it.booking_date)
                if is_closed or not open_time or not close_time:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Gym is closed for one of the selected dates")
                if not it.preferred_start_time or not it.preferred_end_time:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Preferred times missing for gym access")
                if it.preferred_start_time < open_time:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Preferred start time must be within opening hours")
                if it.preferred_end_time > close_time:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Preferred end time must be within opening hours")
                if it.preferred_end_time <= it.preferred_start_time:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Preferred end time must be after start time")

                it.status = CartItemStatus.CONFIRMED.value
                total += Decimal(str(it.total_price or 0)).quantize(Decimal("0.01"))
                confirmed.append(_to_cart_item_response(item=it, gym_name=gym_map.get(int(it.gym_id))))

            elif it.booking_type == BookingType.CLASS.value:
                if it.class_session_id is None:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="class_session_id missing")

                # Lock session row while verifying and incrementing capacity
                row = (
                    db.execute(
                        select(ClassSession, GymClass)
                        .join(GymClass, GymClass.id == ClassSession.gym_class_id)
                        .where(ClassSession.id == it.class_session_id)
                        .with_for_update()
                    )
                    .first()
                )
                if not row:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class session not found")

                sess, gclass = row
                if int(gclass.gym_id) != int(it.gym_id):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Class does not belong to this gym")
                if sess.session_date != it.booking_date:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected date does not match class session")
                if sess.status in {ClassSessionStatus.CANCELLED.value, ClassSessionStatus.CLOSED.value}:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Class session is not bookable")

                max_cap = int(sess.maximum_capacity or 0)
                booked = int(sess.booked_capacity or 0)
                available = max(0, max_cap - booked)
                if available <= 0:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Class is full")
                if available < int(it.member_count):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Only {available} slots are available for this class.",
                    )

                # Reserve capacity
                sess.booked_capacity = booked + int(it.member_count)
                it.status = CartItemStatus.CONFIRMED.value

                total += Decimal(str(it.total_price or 0)).quantize(Decimal("0.01"))
                confirmed.append(
                    _to_cart_item_response(
                        item=it,
                        gym_name=gym_map.get(int(it.gym_id)),
                        class_name=gclass.class_name,
                        start_time=str(sess.start_time),
                        end_time=str(sess.end_time),
                        available_capacity=max(0, max_cap - int(sess.booked_capacity or 0)),
                    )
                )
            else:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown booking_type {it.booking_type}")

        db.commit()
    except Exception:
        db.rollback()
        raise

    return CartCheckoutResponse(confirmed_items=confirmed, total_amount=str(total.quantize(Decimal('0.01'))), currency="INR")


@router.post("/checkout/wallet", response_model=CartWalletCheckoutResponse)
def checkout_cart_with_wallet(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    """Confirm all ACTIVE cart items and pay using FitiGo Wallet.

    - Locks ACTIVE cart items and the user's wallet account row.
    - Validates wallet balance >= cart total.
    - Deducts wallet balance and records a wallet transaction.
    - Confirms cart items (same validations as /cart/checkout).

    This endpoint is intended for the UI flow: Add to Cart -> Proceed -> Checkout Details -> Pay.
    """

    uid = _require_user_id(db, current_user)

    # Lock cart items first (consistent lock ordering for this flow)
    items = (
        db.execute(
            select(CartItem)
            .where(CartItem.user_id == uid, CartItem.status == CartItemStatus.ACTIVE.value)
            .order_by(CartItem.id.asc())
            .with_for_update()
        )
        .scalars()
        .all()
    )
    if not items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cart is empty")

    # Preload gyms names
    gym_ids = sorted({int(i.gym_id) for i in items})
    gym_map: dict[int, str] = {}
    if gym_ids:
        gyms = db.execute(select(Gym).where(Gym.id.in_(gym_ids))).scalars().all()
        gym_map = {int(g.id): g.name for g in gyms}

    # Lock wallet account row.
    acct = (
        db.execute(select(WalletAccount).where(WalletAccount.user_id == uid).with_for_update())
        .scalars()
        .first()
    )
    if not acct:
        acct = WalletAccount(user_id=uid, balance=0, currency="INR")
        db.add(acct)
        db.flush()

    wallet_before = Decimal(str(acct.balance or 0)).quantize(Decimal("0.01"))

    confirmed: list[CartItemResponse] = []
    total = Decimal("0.00")

    try:
        # Validate/confirm items and compute total
        # Collect per-item details needed to create Booking rows (so Profile -> Upcoming Visits works).
        # key = cart_item_id
        item_booking_meta: dict[int, dict] = {}

        for it in items:
            if it.booking_type == BookingType.GYM.value:
                open_time, close_time, is_closed = _operating_hours_for_date(db, gym_id=int(it.gym_id), dt=it.booking_date)
                if is_closed or not open_time or not close_time:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Gym is closed for one of the selected dates")
                if not it.preferred_start_time or not it.preferred_end_time:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Preferred times missing for gym access")
                if it.preferred_start_time < open_time:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Preferred start time must be within opening hours")
                if it.preferred_end_time > close_time:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Preferred end time must be within opening hours")
                if it.preferred_end_time <= it.preferred_start_time:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Preferred end time must be after start time")

                it.status = CartItemStatus.CONFIRMED.value
                total += Decimal(str(it.total_price or 0)).quantize(Decimal("0.01"))
                confirmed.append(_to_cart_item_response(item=it, gym_name=gym_map.get(int(it.gym_id))))

            elif it.booking_type == BookingType.CLASS.value:
                if it.class_session_id is None:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="class_session_id missing")

                row = (
                    db.execute(
                        select(ClassSession, GymClass)
                        .join(GymClass, GymClass.id == ClassSession.gym_class_id)
                        .where(ClassSession.id == it.class_session_id)
                        .with_for_update()
                    )
                    .first()
                )
                if not row:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class session not found")

                sess, gclass = row
                if int(gclass.gym_id) != int(it.gym_id):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Class does not belong to this gym")
                if sess.session_date != it.booking_date:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected date does not match class session")
                if sess.status in {ClassSessionStatus.CANCELLED.value, ClassSessionStatus.CLOSED.value}:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Class session is not bookable")

                max_cap = int(sess.maximum_capacity or 0)
                booked = int(sess.booked_capacity or 0)
                available = max(0, max_cap - booked)
                if available <= 0:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Class is full")
                if available < int(it.member_count):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Only {available} slots are available for this class.",
                    )

                sess.booked_capacity = booked + int(it.member_count)
                it.status = CartItemStatus.CONFIRMED.value

                item_booking_meta[int(it.id)] = {
                    "access_type_id": "GROUP_CLASS",
                    "slot_name": gclass.class_name,
                    "slot_start_time": sess.start_time,
                    "slot_end_time": sess.end_time,
                    "slot_capacity": max_cap,
                    "unit_price": Decimal(str(it.price_per_person or 0)).quantize(Decimal("0.01")),
                }

                total += Decimal(str(it.total_price or 0)).quantize(Decimal("0.01"))
                confirmed.append(
                    _to_cart_item_response(
                        item=it,
                        gym_name=gym_map.get(int(it.gym_id)),
                        class_name=gclass.class_name,
                        start_time=str(sess.start_time),
                        end_time=str(sess.end_time),
                        available_capacity=max(0, max_cap - int(sess.booked_capacity or 0)),
                    )
                )
            else:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown booking_type {it.booking_type}")

            # Meta for gym access booking
            if it.booking_type == BookingType.GYM.value:
                item_booking_meta[int(it.id)] = {
                    "access_type_id": "GYM_WORKOUT",
                    "slot_name": "Gym Access",
                    "slot_start_time": it.preferred_start_time,
                    "slot_end_time": it.preferred_end_time,
                    # Keep large capacity for ad-hoc time ranges.
                    "slot_capacity": 500,
                    "unit_price": Decimal(str(it.price_per_person or 0)).quantize(Decimal("0.01")),
                }

        total = total.quantize(Decimal("0.01"))

        if wallet_before < total:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient wallet balance")

        wallet_after = (wallet_before - total).quantize(Decimal("0.01"))
        acct.balance = float(wallet_after)

        tx = WalletTransaction(
            account_id=int(acct.id),
            user_id=uid,
            direction=WalletTxnDirection.OUT.value,
            txn_type=WalletTxnType.PAYMENT.value,
            amount=float(total),
            currency=acct.currency,
            reference="CART_CHECKOUT",
            description=f"Payment for {len(items)} cart item(s)",
        )
        db.add(tx)

        # --- Create Bookings + Payments (CONFIRMED/PAID) so Profile shows the visits ---
        # NOTE: This is intentionally lightweight and does NOT use SlotAvailability capacity accounting.
        # - CLASS items already reserve capacity using ClassSession.booked_capacity.
        # - GYM items are ad-hoc time windows (preferred_start/end) without slot capacity.
        # We only create Bookings so the Profile -> Upcoming Visits UI can show confirmed visits.
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=15)

        booking_ids: list[int] = []

        for it in items:
            meta = item_booking_meta.get(int(it.id))
            if not meta:
                # Should not happen, but avoid hard-failing wallet debit.
                continue

            slot_name = str(meta["slot_name"])
            slot_start = meta["slot_start_time"]
            slot_end = meta["slot_end_time"]
            slot_capacity = int(meta["slot_capacity"] or 0) or 500
            unit_price = Decimal(str(meta["unit_price"] or 0)).quantize(Decimal("0.01"))

            # Ensure a GymSlot exists for this gym + time window.
            slot = (
                db.execute(
                    select(GymSlot).where(
                        GymSlot.gym_id == int(it.gym_id),
                        GymSlot.start_time == slot_start,
                        GymSlot.end_time == slot_end,
                        GymSlot.name == slot_name,
                        GymSlot.is_active == 1,
                    )
                )
                .scalars()
                .first()
            )
            if not slot:
                slot = GymSlot(
                    gym_id=int(it.gym_id),
                    name=slot_name,
                    start_time=slot_start,
                    end_time=slot_end,
                    capacity=slot_capacity,
                    price=unit_price,  # informational; booking uses unit_price below
                    is_active=1,
                )
                db.add(slot)
                db.flush()

            total_price = (unit_price * Decimal(int(it.member_count))).quantize(Decimal("0.01"))

            notes_parts = [
                f"access_type_id={meta['access_type_id']}",
                f"cart_item_id={int(it.id)}",
            ]
            # Keep some context for debugging.
            if it.booking_type == BookingType.GYM.value:
                notes_parts.append(f"preferred_start_time={slot_start}")
                notes_parts.append(f"preferred_end_time={slot_end}")
            elif it.booking_type == BookingType.CLASS.value and it.class_session_id is not None:
                notes_parts.append(f"class_session_id={int(it.class_session_id)}")

            booking = Booking(
                user_id=uid,
                gym_id=int(it.gym_id),
                gym_slot_id=int(slot.id),
                slot_date=it.booking_date,
                quantity=int(it.member_count),
                unit_price=unit_price,
                total_price=total_price,
                currency=str(it.currency or "INR"),
                status=BookingStatus.CONFIRMED.value,
                notes="\n".join(notes_parts),
                expires_at=expires_at,
                expired_at=None,
                idempotency_key=None,
            )
            db.add(booking)
            db.flush()

            payment = Payment(
                booking_id=int(booking.id),
                provider="WALLET",
                status=PaymentStatus.PAID.value,
                amount=total_price,
                currency=str(it.currency or "INR"),
                external_ref=f"WALLET_TXN:{int(tx.id) if tx.id else 'PENDING'}",
            )
            db.add(payment)

            booking_ids.append(int(booking.id))

        db.commit()
        db.refresh(tx)
    except Exception:
        db.rollback()
        raise

    return CartWalletCheckoutResponse(
        confirmed_items=confirmed,
        total_amount=str(total),
        currency=acct.currency,
        wallet_balance_before=str(wallet_before),
        wallet_balance_after=str(wallet_after),
        wallet_transaction_id=int(tx.id),
        booking_ids=booking_ids,
    )
