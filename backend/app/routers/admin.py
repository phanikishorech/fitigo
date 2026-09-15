from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_role
from app.models.auth import User
from app.core.roles import ROLE_ADMIN, ROLE_SUPER_ADMIN
from app.database.session import get_db
from app.schemas.admin_gym import RejectGymRequest, SuspendGymRequest
from app.schemas.gym import GymListItem
from app.schemas.admin_booking import (
    AdminBookingCustomer,
    AdminBookingGym,
    AdminBookingPayment,
    AdminBookingResponse,
    AdminBookingSlot,
)
from app.services.admin_gym_service import AdminGymService
from app.services.admin_booking_service import AdminBookingService
from app.services.admin_booking_ops_service import AdminBookingOpsService
from app.schemas.admin_booking_ops import AdminForceCancelRequest, AdminUpdatePaymentStatusRequest

from app.schemas.admin_reports import AdminDailyBookingReportRow
from sqlalchemy import case, func, select
from app.models.booking import Booking
from app.models.booking import Payment
from app.services.review_service import ReviewService

from app.schemas.admin_users import AdminUpdateUserStatusRequest, AdminUserDetail, AdminUserListItem
from app.services.admin_user_service import AdminUserService
from app.services.admin_dashboard_service import AdminDashboardService
from app.schemas.admin_gyms import AdminGymListItem as AdminGymListItemSchema


router = APIRouter(prefix="/admin")


@router.post("/reviews/{review_id}/hide", response_model=dict)
def hide_review(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_ADMIN, ROLE_SUPER_ADMIN})),
):
    svc = ReviewService(db)
    svc.set_review_visibility(review_id=review_id, published=False)
    return {"status": "ok"}


@router.post("/reviews/{review_id}/publish", response_model=dict)
def publish_review(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_ADMIN, ROLE_SUPER_ADMIN})),
):
    svc = ReviewService(db)
    svc.set_review_visibility(review_id=review_id, published=True)
    return {"status": "ok"}


@router.post("/gyms/{gym_id}/feature", response_model=dict)
def set_featured(
    gym_id: int,
    featured: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_ADMIN, ROLE_SUPER_ADMIN})),
):
    from app.models.gym import Gym
    from sqlalchemy import select

    g = db.execute(select(Gym).where(Gym.id == gym_id)).scalars().first()
    if not g:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")
    g.is_featured = bool(featured)
    db.commit()
    return {"status": "ok", "gym_id": g.id, "is_featured": g.is_featured}


@router.get("/ping")
def admin_ping(current_user: User = Depends(require_role({ROLE_ADMIN, ROLE_SUPER_ADMIN}))):
    return {"status": "ok", "message": "admin access granted", "user_id": current_user.id}


@router.get("/dashboard/summary", response_model=dict)
def admin_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_ADMIN, ROLE_SUPER_ADMIN})),
):
    svc = AdminDashboardService(db)
    return svc.summary()


@router.get("/users", response_model=list[AdminUserListItem])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_ADMIN, ROLE_SUPER_ADMIN})),
    q: str | None = Query(default=None, max_length=100),
    role: str | None = Query(default=None, max_length=50),
    status_filter: str | None = Query(default=None, alias="status", max_length=50),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    svc = AdminUserService(db)
    users = svc.list_users(q=q, role=role, status_filter=status_filter, limit=limit, offset=offset)
    # Include roles for each user (n+1 for now; ok for admin list limits)
    from app.repositories.user_repository import UserRepository

    repo = UserRepository(db)
    out: list[AdminUserListItem] = []
    for u in users:
        out.append(
            AdminUserListItem(
                id=u.id,
                first_name=u.first_name,
                last_name=u.last_name,
                email=u.email,
                phone=u.phone,
                status=u.status,
                created_at=u.created_at,
                roles=repo.get_role_names(u.id),
            )
        )
    return out


@router.get("/users/{user_id}", response_model=AdminUserDetail)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_ADMIN, ROLE_SUPER_ADMIN})),
):
    svc = AdminUserService(db)
    u = svc.get_user(user_id=user_id)
    from app.repositories.user_repository import UserRepository

    repo = UserRepository(db)
    return AdminUserDetail(
        id=u.id,
        first_name=u.first_name,
        last_name=u.last_name,
        email=u.email,
        phone=u.phone,
        status=u.status,
        created_at=u.created_at,
        roles=repo.get_role_names(u.id),
    )


@router.post("/users/{user_id}/status", response_model=dict)
def update_user_status(
    user_id: int,
    payload: AdminUpdateUserStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_ADMIN, ROLE_SUPER_ADMIN})),
):
    svc = AdminUserService(db)
    u = svc.update_status(user_id=user_id, new_status=payload.status, reason=payload.reason)
    return {"status": "ok", "user_id": u.id, "new_status": u.status}


@router.get("/gyms/pending", response_model=list[GymListItem])
def pending_gyms(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_ADMIN, ROLE_SUPER_ADMIN})),
):
    svc = AdminGymService(db)
    gyms = svc.list_pending()
    return [
        GymListItem(
            id=g.id,
            name=g.name,
            city=g.city,
            status=g.status,
            is_active=g.is_active,
            created_at=g.created_at,
            distance_km=None,
            cover_image_url=None,
        )
        for g in gyms
    ]


@router.get("/gyms", response_model=list[AdminGymListItemSchema])
def list_gyms(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_ADMIN, ROLE_SUPER_ADMIN})),
    q: str | None = Query(default=None, max_length=100),
    status_filter: str | None = Query(default=None, alias="status", max_length=50),
    owner_user_id: int | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    featured: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    from sqlalchemy import or_
    from app.models.gym import Gym

    stmt = select(Gym).order_by(Gym.id.desc()).limit(limit).offset(offset)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Gym.name.like(like), Gym.city.like(like)))
    if status_filter:
        stmt = stmt.where(Gym.status == status_filter)
    if owner_user_id is not None:
        stmt = stmt.where(Gym.owner_user_id == owner_user_id)
    if is_active is not None:
        stmt = stmt.where(Gym.is_active.is_(bool(is_active)))
    if featured is not None:
        stmt = stmt.where(Gym.is_featured.is_(bool(featured)))

    gyms = list(db.execute(stmt).scalars().all())
    return [
        AdminGymListItemSchema(
            id=g.id,
            owner_user_id=g.owner_user_id,
            name=g.name,
            city=g.city,
            status=g.status,
            is_active=bool(g.is_active),
            is_featured=bool(getattr(g, "is_featured", False)),
            created_at=g.created_at,
        )
        for g in gyms
    ]


@router.post("/gyms/{gym_id}/approve", response_model=dict)
def approve_gym(
    gym_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_ADMIN, ROLE_SUPER_ADMIN})),
):
    svc = AdminGymService(db)
    g = svc.approve(gym_id=gym_id, changed_by_user_id=current_user.id)
    return {"status": "ok", "gym_id": g.id, "new_status": g.status}


@router.post("/gyms/{gym_id}/reject", response_model=dict)
def reject_gym(
    gym_id: int,
    payload: RejectGymRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_ADMIN, ROLE_SUPER_ADMIN})),
):
    svc = AdminGymService(db)
    g = svc.reject(gym_id=gym_id, changed_by_user_id=current_user.id, reason=payload.reason)
    return {"status": "ok", "gym_id": g.id, "new_status": g.status}


@router.post("/gyms/{gym_id}/suspend", response_model=dict)
def suspend_gym(
    gym_id: int,
    payload: SuspendGymRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_ADMIN, ROLE_SUPER_ADMIN})),
):
    svc = AdminGymService(db)
    g = svc.suspend(gym_id=gym_id, changed_by_user_id=current_user.id, reason=payload.reason)
    return {"status": "ok", "gym_id": g.id, "new_status": g.status}


@router.post("/gyms/{gym_id}/reactivate", response_model=dict)
def reactivate_gym(
    gym_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_ADMIN, ROLE_SUPER_ADMIN})),
):
    svc = AdminGymService(db)
    g = svc.reactivate(gym_id=gym_id, changed_by_user_id=current_user.id)
    return {"status": "ok", "gym_id": g.id, "new_status": g.status}


@router.get("/bookings", response_model=list[AdminBookingResponse])
def search_bookings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_ADMIN, ROLE_SUPER_ADMIN})),
    q: str | None = Query(default=None, max_length=100),
    gym_id: int | None = Query(default=None),
    owner_user_id: int | None = Query(default=None),
    slot_date: date | None = Query(default=None, alias="date"),
    booking_status: str | None = Query(default=None, alias="status"),
    payment_status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    svc = AdminBookingService(db)
    rows = svc.search(
        q=q,
        gym_id=gym_id,
        owner_user_id=owner_user_id,
        slot_date=slot_date,
        booking_status=booking_status,
        payment_status=payment_status,
        limit=limit,
        offset=offset,
    )

    out: list[AdminBookingResponse] = []
    for b, u, g, s, p in rows:
        out.append(
            AdminBookingResponse(
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
                attendance_status=b.attendance_status,
                attendance_marked_at=b.attendance_marked_at,
                attendance_note=b.attendance_note,
                customer=AdminBookingCustomer(
                    id=u.id,
                    first_name=u.first_name,
                    last_name=u.last_name,
                    email=u.email,
                    phone=u.phone,
                ),
                gym=AdminBookingGym(
                    id=g.id,
                    name=g.name,
                    city=g.city,
                    status=g.status,
                    is_active=g.is_active,
                    owner_user_id=g.owner_user_id,
                ),
                slot=AdminBookingSlot(
                    id=s.id,
                    name=s.name,
                    start_time=s.start_time,
                    end_time=s.end_time,
                ),
                payment=(
                    AdminBookingPayment(
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


@router.get("/bookings/{booking_id}", response_model=AdminBookingResponse)
def get_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_ADMIN, ROLE_SUPER_ADMIN})),
):
    svc = AdminBookingService(db)
    b, u, g, s, p = svc.get(booking_id=booking_id)
    return AdminBookingResponse(
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
        attendance_status=b.attendance_status,
        attendance_marked_at=b.attendance_marked_at,
        attendance_note=b.attendance_note,
        customer=AdminBookingCustomer(
            id=u.id,
            first_name=u.first_name,
            last_name=u.last_name,
            email=u.email,
            phone=u.phone,
        ),
        gym=AdminBookingGym(
            id=g.id,
            name=g.name,
            city=g.city,
            status=g.status,
            is_active=g.is_active,
            owner_user_id=g.owner_user_id,
        ),
        slot=AdminBookingSlot(
            id=s.id,
            name=s.name,
            start_time=s.start_time,
            end_time=s.end_time,
        ),
        payment=(
            AdminBookingPayment(
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


@router.post("/bookings/{booking_id}/cancel", response_model=dict)
def admin_cancel_booking(
    booking_id: int,
    payload: AdminForceCancelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_ADMIN, ROLE_SUPER_ADMIN})),
):
    svc = AdminBookingOpsService(db)
    b = svc.cancel_booking(booking_id=booking_id, reason=payload.reason)
    return {"status": "ok", "booking_id": b.id, "new_status": b.status}


@router.post("/bookings/{booking_id}/payment/status", response_model=dict)
def admin_update_payment_status(
    booking_id: int,
    payload: AdminUpdatePaymentStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_ADMIN, ROLE_SUPER_ADMIN})),
):
    svc = AdminBookingOpsService(db)
    b = svc.update_payment_status(
        booking_id=booking_id,
        new_status=payload.status,
        external_ref=payload.external_ref,
        note=payload.note,
    )
    return {"status": "ok", "booking_id": b.id}


@router.get("/reports/bookings/daily", response_model=list[AdminDailyBookingReportRow])
def report_daily_bookings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_ADMIN, ROLE_SUPER_ADMIN})),
    gym_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=31, ge=1, le=366),
):
    # Aggregate by slot_date
    stmt = (
        select(
            Booking.slot_date.label("day"),
            func.count(Booking.id).label("total_bookings"),
            func.sum(case((Booking.status == "CONFIRMED", 1), else_=0)).label("confirmed_bookings"),
            func.sum(case((Booking.status == "CANCELLED", 1), else_=0)).label("cancelled_bookings"),
            func.sum(case((Booking.status == "EXPIRED", 1), else_=0)).label("expired_bookings"),
            func.sum(case((Payment.status == "PAID", Payment.amount), else_=0)).label("paid_amount_total"),
        )
        .select_from(Booking)
        .outerjoin(Payment, Payment.booking_id == Booking.id)
        .group_by(Booking.slot_date)
        .order_by(Booking.slot_date.desc())
        .limit(limit)
    )

    if gym_id is not None:
        stmt = stmt.where(Booking.gym_id == gym_id)
    if date_from is not None:
        stmt = stmt.where(Booking.slot_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Booking.slot_date <= date_to)

    rows = db.execute(stmt).all()
    return [
        AdminDailyBookingReportRow(
            day=r.day,
            total_bookings=int(r.total_bookings or 0),
            confirmed_bookings=int(r.confirmed_bookings or 0),
            cancelled_bookings=int(r.cancelled_bookings or 0),
            expired_bookings=int(r.expired_bookings or 0),
            paid_amount_total=str(r.paid_amount_total or 0),
        )
        for r in rows
    ]
