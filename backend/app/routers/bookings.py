from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.dependencies import require_role
from app.core.roles import ROLE_CUSTOMER
from app.database.session import get_db
from app.models.auth import User
from app.models.booking import Booking, Payment
from app.schemas.booking import (
    BookingCancelRequest,
    BookingCreateRequest,
    BookingRescheduleRequest,
    BookingResponse,
    PaymentResponse,
)
from app.services.booking_service import BookingService
from sqlalchemy import select


router = APIRouter(prefix="/bookings")


def _to_payment_response(p: Payment | None) -> PaymentResponse | None:
    if not p:
        return None
    return PaymentResponse(
        id=p.id,
        provider=p.provider,
        status=p.status,
        amount=str(p.amount),
        currency=p.currency,
        external_ref=p.external_ref,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _to_booking_response(b: Booking) -> BookingResponse:
    return BookingResponse(
        id=b.id,
        user_id=b.user_id,
        gym_id=b.gym_id,
        gym_slot_id=b.gym_slot_id,
        slot_date=b.slot_date,
        quantity=b.quantity,
        unit_price=str(b.unit_price),
        total_price=str(b.total_price),
        currency=b.currency,
        status=b.status,
        notes=b.notes,
        expires_at=b.expires_at,
        expired_at=b.expired_at,
        created_at=b.created_at,
        updated_at=b.updated_at,
        cancelled_at=b.cancelled_at,
        payment=_to_payment_response(b.payment if hasattr(b, "payment") else None),
    )


@router.post("", response_model=BookingResponse)
def create_booking(
    payload: BookingCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_CUSTOMER})),
):
    svc = BookingService(db)
    booking = svc.create_booking(
        user_id=current_user.id,
        gym_slot_id=payload.gym_slot_id,
        slot_date=payload.slot_date,
        quantity=payload.quantity,
        notes=payload.notes,
        idempotency_key=idempotency_key,
    )
    # load payment relationship
    booking = db.execute(select(Booking).where(Booking.id == booking.id)).scalars().first() or booking
    return _to_booking_response(booking)


@router.get("/me", response_model=list[BookingResponse])
def list_my_bookings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_CUSTOMER})),
):
    items = (
        db.execute(select(Booking).where(Booking.user_id == current_user.id).order_by(Booking.id.desc()))
        .scalars()
        .all()
    )
    return [_to_booking_response(b) for b in items]


@router.get("/{booking_id}", response_model=BookingResponse)
def get_my_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_CUSTOMER})),
):
    b = db.execute(select(Booking).where(Booking.id == booking_id, Booking.user_id == current_user.id)).scalars().first()
    if not b:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    return _to_booking_response(b)


@router.post("/{booking_id}/pay", response_model=BookingResponse)
def pay_dummy(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_CUSTOMER})),
):
    svc = BookingService(db)
    booking = svc.pay_dummy(user_id=current_user.id, booking_id=booking_id)
    booking = db.execute(select(Booking).where(Booking.id == booking.id)).scalars().first() or booking
    return _to_booking_response(booking)


@router.post("/{booking_id}/cancel", response_model=BookingResponse)
def cancel_booking(
    booking_id: int,
    payload: BookingCancelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_CUSTOMER})),
):
    svc = BookingService(db)
    booking = svc.cancel_booking(user_id=current_user.id, booking_id=booking_id, reason=payload.reason)
    booking = db.execute(select(Booking).where(Booking.id == booking.id)).scalars().first() or booking
    return _to_booking_response(booking)


@router.post("/{booking_id}/reschedule", response_model=BookingResponse)
def reschedule_booking(
    booking_id: int,
    payload: BookingRescheduleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_CUSTOMER})),
):
    svc = BookingService(db)
    booking = svc.reschedule_booking(
        user_id=current_user.id,
        booking_id=booking_id,
        new_gym_slot_id=payload.gym_slot_id,
        new_slot_date=payload.slot_date,
        note=payload.note,
    )
    booking = db.execute(select(Booking).where(Booking.id == booking.id)).scalars().first() or booking
    return _to_booking_response(booking)
