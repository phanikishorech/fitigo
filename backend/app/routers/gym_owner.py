from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.dependencies import require_role
from app.core.roles import ROLE_GYM_OWNER
from app.database.session import get_db
from app.models.auth import User
from sqlalchemy import select

from app.models.gym import Gym, GymFacility, GymFacilityMapping, GymImage, GymOperatingHours
from app.repositories.gym_repository import GymRepository
from app.schemas.gym import (
    GymCreateRequest,
    GymListItem,
    GymResponse,
    GymUpdateRequest,
    SetGymFacilitiesRequest,
    SetGymOperatingHoursRequest,
)
from app.services.gym_service import GymService
from app.services.slot_service import SlotService
from app.services.booking_service import BookingService
from app.services.staff_service import StaffService
from app.services.owner_dashboard_service import OwnerDashboardService
from app.storage.local import LocalStorageService
from app.schemas.slot import GymSlotCreateRequest, GymSlotOwnerResponse, GymSlotUpdateRequest
from app.schemas.booking_owner import OwnerBookingActionRequest, OwnerBookingResponse
from app.schemas.booking_owner import OwnerBookingCustomer, OwnerBookingPayment, OwnerBookingSlot
from app.schemas.staff import InviteStaffRequest, StaffAssignmentResponse

from app.schemas.membership import MembershipPlanCreateRequest, MembershipPlanResponse, MembershipPlanUpdateRequest
from app.services.membership_service import MembershipService


router = APIRouter(prefix="/gym-owner")


def _to_membership_plan_response(p) -> MembershipPlanResponse:
    return MembershipPlanResponse(
        id=p.id,
        gym_id=p.gym_id,
        name=p.name,
        description=p.description,
        duration_days=p.duration_days,
        price=str(p.price),
        currency=p.currency,
        is_active=p.is_active,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _validate_image(upload: UploadFile, max_bytes: int = 5 * 1024 * 1024) -> None:
    if upload.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid image type")

    # best-effort size check (spools to temp file for large uploads)
    upload.file.seek(0, 2)
    size = upload.file.tell()
    upload.file.seek(0)
    if size > max_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File too large")


@router.post("/gyms", response_model=GymResponse)
def create_gym(
    payload: GymCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = GymService(db)
    gym = svc.create_gym(owner_user_id=current_user.id, data=payload.model_dump())
    return _to_gym_response(db, gym.id)


@router.get("/gyms", response_model=list[GymListItem])
def list_my_gyms(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    repo = GymRepository(db)
    # Include cover image URL if present
    cover_path = (
        select(GymImage.file_path)
        .where(GymImage.gym_id == Gym.id, GymImage.is_cover.is_(True))
        .order_by(GymImage.id.asc())
        .limit(1)
        .scalar_subquery()
    )
    rows = (
        db.execute(
            select(Gym, cover_path.label("cover_path")).where(Gym.owner_user_id == current_user.id).order_by(Gym.id.desc())
        )
        .all()
    )
    return [
        GymListItem(
            id=g.id,
            name=g.name,
            city=g.city,
            status=g.status,
            is_active=g.is_active,
            created_at=g.created_at,
            distance_km=None,
            cover_image_url=(f"/uploads/{cp}" if cp else None),
        )
        for g, cp in rows
    ]


@router.get("/gyms/{gym_id}", response_model=GymResponse)
def get_my_gym(
    gym_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    gym = db.execute(select(Gym).where(Gym.id == gym_id, Gym.owner_user_id == current_user.id)).scalars().first()
    if not gym:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")
    return _to_gym_response(db, gym_id)


@router.get("/gyms/{gym_id}/slots", response_model=list[GymSlotOwnerResponse])
def list_my_slots(
    gym_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = SlotService(db)
    slots = svc.list_owner_slots(owner_user_id=current_user.id, gym_id=gym_id)
    return [
        GymSlotOwnerResponse(
            id=s.id,
            gym_id=s.gym_id,
            name=s.name,
            start_time=s.start_time,
            end_time=s.end_time,
            capacity=s.capacity,
            price=str(s.price),
            is_active=bool(s.is_active == 1),
        )
        for s in slots
    ]


@router.put("/gyms/{gym_id}/images/{image_id}/set-cover", response_model=dict)
def set_cover_image(
    gym_id: int,
    image_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = GymService(db)
    img = svc.set_cover_image(owner_user_id=current_user.id, gym_id=gym_id, image_id=image_id)
    return {"status": "ok", "image_id": img.id, "file_path": img.file_path, "url": f"/uploads/{img.file_path}"}


@router.get("/dashboard/summary", response_model=dict)
def owner_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = OwnerDashboardService(db)
    return svc.summary(owner_user_id=current_user.id)


@router.put("/gyms/{gym_id}", response_model=GymResponse)
def update_gym(
    gym_id: int,
    payload: GymUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = GymService(db)
    gym = svc.update_gym(owner_user_id=current_user.id, gym_id=gym_id, data=payload.model_dump(exclude_unset=True))
    return _to_gym_response(db, gym.id)


def _to_gym_response(db: Session, gym_id: int) -> GymResponse:
    gym = GymRepository(db).get_gym_by_id(gym_id)
    if not gym:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

    images = list(db.execute(select(GymImage).where(GymImage.gym_id == gym_id).order_by(GymImage.id.asc())).scalars().all())

    # Facilities
    facs = (
        db.execute(
            select(GymFacility)
            .join(GymFacilityMapping, GymFacilityMapping.facility_id == GymFacility.id)
            .where(GymFacilityMapping.gym_id == gym_id)
            .order_by(GymFacility.name.asc())
        )
        .scalars()
        .all()
    )

    hours = list(
        db.execute(
            select(GymOperatingHours)
            .where(GymOperatingHours.gym_id == gym_id)
            .order_by(GymOperatingHours.day_of_week.asc())
        )
        .scalars()
        .all()
    )

    return GymResponse(
        id=gym.id,
        owner_user_id=gym.owner_user_id,
        name=gym.name,
        description=gym.description,
        phone=gym.phone,
        email=gym.email,
        address_line_1=gym.address_line_1,
        address_line_2=gym.address_line_2,
        city=gym.city,
        state=gym.state,
        country=gym.country,
        postal_code=gym.postal_code,
        latitude=gym.latitude,
        longitude=gym.longitude,
        status=gym.status,
        is_active=gym.is_active,
        gym_price_per_person=str(getattr(gym, "gym_price_per_person", 0) or 0),
        has_classes=bool(getattr(gym, "has_classes", False)),
        created_at=gym.created_at,
        updated_at=gym.updated_at,
        images=[
            {
                "id": i.id,
                "file_path": i.file_path,
                "original_filename": i.original_filename,
                "image_type": i.image_type,
                "display_order": i.display_order,
                "is_cover": i.is_cover,
                "created_at": i.created_at,
            }
            for i in images
        ],
        facilities=[
            {
                "id": f.id,
                "name": f.name,
                "description": f.description,
                "icon": f.icon,
            }
            for f in facs
        ],
        operating_hours=[
            {
                "day_of_week": h.day_of_week,
                "open_time": h.open_time,
                "close_time": h.close_time,
                "is_closed": h.is_closed,
            }
            for h in hours
        ],
    )


@router.post("/gyms/{gym_id}/submit", response_model=dict)
def submit_gym(
    gym_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = GymService(db)
    gym = svc.submit_for_approval(owner_user_id=current_user.id, gym_id=gym_id)
    return {"status": "ok", "gym_id": gym.id, "new_status": gym.status}


@router.post("/gyms/{gym_id}/images", response_model=dict)
def upload_gym_image(
    gym_id: int,
    file: UploadFile = File(...),
    is_cover: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    _validate_image(file)
    storage = LocalStorageService()
    rel_path = storage.save_gym_image(
        gym_id=gym_id,
        filename=file.filename or "image",
        content_type=file.content_type or "application/octet-stream",
        fileobj=file.file,
    )

    svc = GymService(db)
    img = svc.add_image(
        owner_user_id=current_user.id,
        gym_id=gym_id,
        file_path=rel_path,
        original_filename=file.filename or "",
        content_type=file.content_type or "",
        is_cover=is_cover,
    )
    return {"status": "ok", "image_id": img.id, "file_path": img.file_path, "url": f"/uploads/{img.file_path}"}


@router.put("/gyms/{gym_id}/facilities", response_model=dict)
def set_facilities(
    gym_id: int,
    payload: SetGymFacilitiesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = GymService(db)
    svc.set_facilities(owner_user_id=current_user.id, gym_id=gym_id, facility_ids=payload.facility_ids)
    return {"status": "ok"}


@router.put("/gyms/{gym_id}/operating-hours", response_model=dict)
def set_operating_hours(
    gym_id: int,
    payload: SetGymOperatingHoursRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = GymService(db)
    svc.set_operating_hours(owner_user_id=current_user.id, gym_id=gym_id, items=[i.model_dump() for i in payload.items])
    return {"status": "ok"}


@router.get("/gyms/{gym_id}/membership-plans", response_model=list[MembershipPlanResponse])
def owner_list_membership_plans(
    gym_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = MembershipService(db)
    plans = svc.list_owner_plans(owner_user_id=current_user.id, gym_id=gym_id)
    return [_to_membership_plan_response(p) for p in plans]


@router.post("/gyms/{gym_id}/membership-plans", response_model=MembershipPlanResponse)
def owner_create_membership_plan(
    gym_id: int,
    payload: MembershipPlanCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = MembershipService(db)
    plan = svc.create_plan(owner_user_id=current_user.id, gym_id=gym_id, data=payload.model_dump())
    return _to_membership_plan_response(plan)


@router.put("/membership-plans/{plan_id}", response_model=MembershipPlanResponse)
def owner_update_membership_plan(
    plan_id: int,
    payload: MembershipPlanUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = MembershipService(db)
    plan = svc.update_plan(owner_user_id=current_user.id, plan_id=plan_id, data=payload.model_dump(exclude_unset=True))
    return _to_membership_plan_response(plan)


@router.delete("/membership-plans/{plan_id}", response_model=dict)
def owner_deactivate_membership_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = MembershipService(db)
    _ = svc.set_plan_active(owner_user_id=current_user.id, plan_id=plan_id, active=False)
    return {"status": "ok"}


@router.post("/membership-plans/{plan_id}/activate", response_model=dict)
def owner_activate_membership_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = MembershipService(db)
    _ = svc.set_plan_active(owner_user_id=current_user.id, plan_id=plan_id, active=True)
    return {"status": "ok"}


@router.post("/gyms/{gym_id}/slots", response_model=dict)
def create_slot(
    gym_id: int,
    payload: GymSlotCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = SlotService(db)
    slot = svc.create_slot(owner_user_id=current_user.id, gym_id=gym_id, data=payload.model_dump())
    return {"status": "ok", "slot_id": slot.id}


@router.put("/slots/{slot_id}", response_model=dict)
def update_slot(
    slot_id: int,
    payload: GymSlotUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = SlotService(db)
    slot = svc.update_slot(owner_user_id=current_user.id, slot_id=slot_id, data=payload.model_dump(exclude_unset=True))
    return {"status": "ok", "slot_id": slot.id}


@router.delete("/slots/{slot_id}", response_model=dict)
def delete_slot(
    slot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = SlotService(db)
    svc.deactivate_slot(owner_user_id=current_user.id, slot_id=slot_id)
    return {"status": "ok"}


@router.post("/gyms/{gym_id}/staff/invite", response_model=dict)
def invite_staff(
    gym_id: int,
    payload: InviteStaffRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = StaffService(db)
    res = svc.invite_staff(
        owner_user_id=current_user.id,
        gym_id=gym_id,
        email=str(payload.email).lower(),
        first_name=payload.first_name,
        last_name=payload.last_name,
    )
    # temp_password returned only when a new user is created
    return {"status": "ok", **res}


@router.get("/gyms/{gym_id}/staff", response_model=list[StaffAssignmentResponse])
def list_staff(
    gym_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = StaffService(db)
    items = svc.list_gym_staff(owner_user_id=current_user.id, gym_id=gym_id)
    return [StaffAssignmentResponse(id=a.id, gym_id=a.gym_id, user_id=a.user_id, role=a.role) for a in items]


@router.delete("/gyms/{gym_id}/staff/{user_id}", response_model=dict)
def remove_staff(
    gym_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = StaffService(db)
    svc.remove_staff(owner_user_id=current_user.id, gym_id=gym_id, user_id=user_id)
    return {"status": "ok"}


@router.get("/gyms/{gym_id}/bookings", response_model=list[OwnerBookingResponse])
def list_gym_bookings(
    gym_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
    slot_date: str | None = Query(default=None, alias="date"),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    # Parse date string if provided to avoid FastAPI type adapter needing date import here.
    parsed_date = None
    if slot_date:
        from datetime import date as _date

        parsed_date = _date.fromisoformat(slot_date)

    svc = BookingService(db)
    rows = svc.list_owner_gym_bookings(
        owner_user_id=current_user.id,
        gym_id=gym_id,
        slot_date=parsed_date,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )

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


@router.get("/bookings/{booking_id}", response_model=OwnerBookingResponse)
def get_booking_detail(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = BookingService(db)
    b, u, s, p = svc.get_owner_booking(owner_user_id=current_user.id, booking_id=booking_id)
    return OwnerBookingResponse(
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


@router.post("/bookings/{booking_id}/cancel", response_model=OwnerBookingResponse)
def owner_cancel_booking(
    booking_id: int,
    payload: OwnerBookingActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = BookingService(db)
    b = svc.owner_cancel_booking(owner_user_id=current_user.id, booking_id=booking_id, reason=payload.reason)
    b2, u, s, p = svc.get_owner_booking(owner_user_id=current_user.id, booking_id=b.id)
    return OwnerBookingResponse(
        id=b2.id,
        gym_id=b2.gym_id,
        gym_slot_id=b2.gym_slot_id,
        slot_date=b2.slot_date,
        quantity=b2.quantity,
        unit_price=str(b2.unit_price),
        total_price=str(b2.total_price),
        currency=b2.currency,
        status=b2.status,
        notes=b2.notes,
        expires_at=b2.expires_at,
        expired_at=b2.expired_at,
        created_at=b2.created_at,
        updated_at=b2.updated_at,
        cancelled_at=b2.cancelled_at,
        attendance_status=b2.attendance_status,
        attendance_marked_at=b2.attendance_marked_at,
        attendance_note=b2.attendance_note,
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


@router.post("/bookings/{booking_id}/mark-attended", response_model=OwnerBookingResponse)
def owner_mark_attended(
    booking_id: int,
    payload: OwnerBookingActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = BookingService(db)
    _ = svc.owner_mark_attendance(owner_user_id=current_user.id, booking_id=booking_id, attendance_status="ATTENDED", note=payload.note)
    b, u, s, p = svc.get_owner_booking(owner_user_id=current_user.id, booking_id=booking_id)
    return OwnerBookingResponse(
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


@router.post("/bookings/{booking_id}/mark-no-show", response_model=OwnerBookingResponse)
def owner_mark_no_show(
    booking_id: int,
    payload: OwnerBookingActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_GYM_OWNER})),
):
    svc = BookingService(db)
    _ = svc.owner_mark_attendance(owner_user_id=current_user.id, booking_id=booking_id, attendance_status="NO_SHOW", note=payload.note)
    b, u, s, p = svc.get_owner_booking(owner_user_id=current_user.id, booking_id=booking_id)
    return OwnerBookingResponse(
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
