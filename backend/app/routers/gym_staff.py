from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import require_role
from app.core.roles import ROLE_GYM_STAFF
from app.database.session import get_db
from app.models.auth import User
from app.models.booking import Booking
from app.models.gym import Gym
from app.models.membership import MembershipDailyAccess, MembershipStatus, UserMembership
from app.models.slot import GymSlot
from app.schemas.booking_owner import OwnerBookingActionRequest, OwnerBookingCustomer, OwnerBookingPayment, OwnerBookingResponse, OwnerBookingSlot
from app.schemas.membership_access import ScanMembershipQRRequest, ScanMembershipQRResponse
from app.services.booking_service import BookingService
from app.services.staff_service import StaffService
from app.services.access_service import AccessService
from app.models.access import AccessQrToken, CustomerDailyAccess
import hashlib


router = APIRouter(prefix="/gym-staff")


@router.post("/scan-membership-qr", response_model=ScanMembershipQRResponse, deprecated=True)
def scan_membership_qr(
    payload: ScanMembershipQRRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_STAFF})),
):
    """Legacy transport, shared validation and one-time-use transaction.

    Existing JWT credentials are deliberately rejected. Customers must refresh
    their pass to obtain an opaque token from the unified issuer.
    """
    assigned = set(StaffService(db).staff_gym_ids(staff_user_id=current_user.id))
    gym_id = payload.gym_id
    if gym_id is None:
        if len(assigned) != 1:
            raise HTTPException(status_code=400, detail="Select a scanning gym using gym_id")
        gym_id = next(iter(assigned))
    if gym_id not in assigned:
        raise HTTPException(status_code=404, detail="Gym not found")
    result = AccessService(db).validate_checkin(gym_id=gym_id, qr_token=payload.qr_payload)
    token_hash = hashlib.sha256(payload.qr_payload.removeprefix("GYMACCESS:").encode()).hexdigest()
    daily = db.execute(select(CustomerDailyAccess).join(
        AccessQrToken, AccessQrToken.daily_access_id == CustomerDailyAccess.id,
    ).where(AccessQrToken.token_hash == token_hash)).scalar_one()
    return ScanMembershipQRResponse(
        gym_id=gym_id, user_id=daily.user_id, access_date=daily.access_date,
        status="SCANNED", scanned_at=result["checkin_time"],
    )


@router.get("/gyms", response_model=list[dict])
def list_my_gyms(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_STAFF})),
):
    svc = StaffService(db)
    gym_ids = svc.staff_gym_ids(staff_user_id=current_user.id)
    gyms = list(db.execute(select(Gym).where(Gym.id.in_(gym_ids))).scalars().all()) if gym_ids else []
    return [{"id": g.id, "name": g.name, "city": g.city} for g in gyms]


@router.get("/gyms/{gym_id}/bookings", response_model=list[OwnerBookingResponse])
def list_gym_bookings(
    gym_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_STAFF})),
    slot_date: Annotated[date | None, Query(alias="date")] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    svc_staff = StaffService(db)
    if gym_id not in set(svc_staff.staff_gym_ids(staff_user_id=current_user.id)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

    svc = BookingService(db)
    rows = svc.list_owner_gym_bookings(owner_user_id=db.execute(select(Gym.owner_user_id).where(Gym.id == gym_id)).scalar_one(), gym_id=gym_id, slot_date=slot_date, limit=limit, offset=offset)

    # rows already include user and payment and slot
    out: list[OwnerBookingResponse] = []
    for b, u, s, p in rows:
        out.append(
            OwnerBookingResponse(
                id=b.id,
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
                attendance_status=b.attendance_status,
                attendance_marked_at=b.attendance_marked_at,
                attendance_note=b.attendance_note,
                customer=OwnerBookingCustomer(
                    id=u.id,
                    first_name=u.first_name,
                    last_name=u.last_name,
                    email=u.email,
                    phone=u.phone,
                ),
                slot=OwnerBookingSlot(
                    id=s.id,
                    name=s.name,
                    start_time=s.start_time,
                    end_time=s.end_time,
                ),
                payment=(
                    OwnerBookingPayment(
                        id=p.id,
                        provider=p.provider,
                        status=p.status,
                        amount=str(p.amount),
                        currency=p.currency,
                        external_ref=p.external_ref,
                    )
                    if p
                    else None
                ),
            )
        )
    return out


@router.post("/bookings/{booking_id}/mark-attended", response_model=dict)
def mark_attended(
    booking_id: int,
    payload: OwnerBookingActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_STAFF})),
):
    # Verify staff belongs to booking's gym
    b = db.execute(select(Booking).where(Booking.id == booking_id)).scalars().first()
    if not b:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    svc_staff = StaffService(db)
    if b.gym_id not in set(svc_staff.staff_gym_ids(staff_user_id=current_user.id)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    svc = BookingService(db)
    # reuse owner-mark logic with gym owner id
    owner_id = db.execute(select(Gym.owner_user_id).where(Gym.id == b.gym_id)).scalar_one()
    svc.owner_mark_attendance(owner_user_id=owner_id, booking_id=booking_id, attendance_status="ATTENDED", note=payload.note)
    return {"status": "ok"}


@router.post("/bookings/{booking_id}/mark-no-show", response_model=dict)
def mark_no_show(
    booking_id: int,
    payload: OwnerBookingActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_STAFF})),
):
    b = db.execute(select(Booking).where(Booking.id == booking_id)).scalars().first()
    if not b:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    svc_staff = StaffService(db)
    if b.gym_id not in set(svc_staff.staff_gym_ids(staff_user_id=current_user.id)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    svc = BookingService(db)
    owner_id = db.execute(select(Gym.owner_user_id).where(Gym.id == b.gym_id)).scalar_one()
    svc.owner_mark_attendance(owner_user_id=owner_id, booking_id=booking_id, attendance_status="NO_SHOW", note=payload.note)
    return {"status": "ok"}
