from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from jose import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_optional_user
from app.database.session import get_db
from app.models.auth import User
from app.models.booking import Booking, BookingStatus
from app.models.gym import Gym
from app.models.membership import GymMembershipPlan, MembershipStatus, UserMembership
from app.models.slot import GymSlot
from app.schemas.profile import (
    BookingItemResponse,
    FavoritesResponse,
    MembershipPassResponse,
    MembershipSummaryResponse,
    ProfileActivityResponse,
    ProfileResponse,
)


router = APIRouter(prefix="/profile")


def _get_dev_customer_id(db: Session) -> int | None:
    """Dev-only fallback when frontend isn't sending Authorization yet."""

    if settings.environment != "development":
        return None
    u = db.execute(select(User).where(User.email == "customer@example.com")).scalars().first()
    return int(u.id) if u else None


def _require_user_id(db: Session, current_user: User | None) -> int:
    uid = int(current_user.id) if current_user else _get_dev_customer_id(db)
    if uid is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return uid


def _parse_notes(notes: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not notes:
        return out
    for line in notes.splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k:
            out[k] = v
    return out


def _access_type_label(access_type_id: str | None) -> str:
    if access_type_id == "DAY_PASS":
        return "Day Pass"
    if access_type_id == "GROUP_CLASS":
        return "Group Class"
    if access_type_id:
        return access_type_id.replace("_", " ").title()
    return "Gym Workout"


def _compute_streak(attended_dates: list[date]) -> int:
    if not attended_dates:
        return 0
    uniq = sorted(set(attended_dates), reverse=True)
    streak = 1
    for i in range(1, len(uniq)):
        if uniq[i - 1] - uniq[i] == timedelta(days=1):
            streak += 1
        else:
            break
    return streak


@router.get("", response_model=ProfileResponse)
def get_profile(db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    uid = _require_user_id(db, current_user)
    user = db.execute(select(User).where(User.id == uid)).scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    full_name = " ".join([p for p in [user.first_name, user.last_name] if p]) or "Member"

    now = datetime.utcnow()
    active = (
        db.execute(
            select(UserMembership)
            .where(
                UserMembership.user_id == uid,
                UserMembership.status == MembershipStatus.ACTIVE.value,
                UserMembership.end_at > now,
            )
            .order_by(UserMembership.end_at.desc())
        )
        .scalars()
        .first()
    )

    membership_status = None
    if active:
        membership_status = "ACTIVE"
    else:
        latest = (
            db.execute(select(UserMembership).where(UserMembership.user_id == uid).order_by(UserMembership.end_at.desc()))
            .scalars()
            .first()
        )
        if latest and latest.end_at <= now:
            membership_status = "EXPIRED"

    return ProfileResponse(
        user_id=uid,
        full_name=full_name,
        profile_image=None,
        member_since=user.created_at,
        membership_status=membership_status,
    )


@router.get("/membership", response_model=MembershipSummaryResponse)
def get_membership_summary(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    uid = _require_user_id(db, current_user)
    now = datetime.utcnow()

    # Active memberships (we treat multiple active gym memberships as "multi-gym" access in UI)
    active_memberships = list(
        db.execute(
            select(UserMembership)
            .where(
                UserMembership.user_id == uid,
                UserMembership.status == MembershipStatus.ACTIVE.value,
                UserMembership.end_at > now,
            )
            .order_by(UserMembership.end_at.desc())
        )
        .scalars()
        .all()
    )

    m = active_memberships[0] if active_memberships else (
        db.execute(select(UserMembership).where(UserMembership.user_id == uid).order_by(UserMembership.end_at.desc())).scalars().first()
    )

    plan_name = None
    if m:
        plan = db.execute(select(GymMembershipPlan).where(GymMembershipPlan.id == m.plan_id)).scalars().first()
        plan_name = plan.name if plan else None

    gym_access_count = len({int(x.gym_id) for x in active_memberships})
    membership_scope = None
    if gym_access_count == 1:
        membership_scope = "SINGLE_GYM"
    elif gym_access_count > 1:
        membership_scope = "MULTI_GYM"

    # Gym details for active memberships
    active_gym_ids = [int(x.gym_id) for x in active_memberships]
    active_gyms: list[dict] = []
    if active_gym_ids:
        gyms = list(db.execute(select(Gym).where(Gym.id.in_(active_gym_ids))).scalars().all())
        gym_map = {int(g.id): g for g in gyms}
        for gid in active_gym_ids:
            g = gym_map.get(int(gid))
            if not g:
                continue
            active_gyms.append(
                {
                    "gym_id": int(g.id),
                    "gym_name": g.name,
                    "locality": g.address_line_2,
                    "city": g.city,
                }
            )

    # Usage stats from bookings (membership-covered = ₹0 confirmed bookings)
    visits_booked: int | None = None
    visits_completed: int | None = None
    if m and active_gym_ids:
        start_d = m.start_at.date() if m.start_at else None
        end_d = m.end_at.date() if m.end_at else None
        if start_d and end_d:
            booked = int(
                db.execute(
                    select(func.count(Booking.id)).where(
                        Booking.user_id == uid,
                        Booking.gym_id.in_(active_gym_ids),
                        Booking.status == BookingStatus.CONFIRMED.value,
                        Booking.total_price <= 0,
                        Booking.slot_date >= start_d,
                        Booking.slot_date <= end_d,
                    )
                ).scalar_one()
                or 0
            )
            completed = int(
                db.execute(
                    select(func.count(Booking.id)).where(
                        Booking.user_id == uid,
                        Booking.gym_id.in_(active_gym_ids),
                        Booking.status == BookingStatus.CONFIRMED.value,
                        Booking.total_price <= 0,
                        Booking.attendance_status == "ATTENDED",
                        Booking.slot_date >= start_d,
                        Booking.slot_date <= end_d,
                    )
                ).scalar_one()
                or 0
            )
            visits_booked = booked
            visits_completed = completed

    # Pause policy constants (MVP)
    pause_days_max = 60
    pause_days_used = 0
    pause_days_remaining = pause_days_max

    return MembershipSummaryResponse(
        membership_id=int(m.id) if m else None,
        plan_name=plan_name,
        status=(m.status if m else None),
        start_date=(m.start_at if m else None),
        end_date=(m.end_at if m else None),
        membership_scope=membership_scope,
        active_gyms=active_gyms,
        gym_access_count=int(gym_access_count or 0),
        remaining_visits=None,
        total_visits=None,
        visits_booked=visits_booked,
        visits_completed=visits_completed,
        pause_days_used=pause_days_used,
        pause_days_remaining=pause_days_remaining,
        membership_features=[],
    )


@router.get("/bookings", response_model=list[BookingItemResponse])
def list_profile_bookings(
    status_filter: str | None = Query(default="upcoming", alias="status"),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    uid = _require_user_id(db, current_user)
    today = datetime.utcnow().date()

    stmt = (
        select(Booking, Gym, GymSlot)
        .join(Gym, Gym.id == Booking.gym_id)
        .join(GymSlot, GymSlot.id == Booking.gym_slot_id)
        .where(Booking.user_id == uid)
        .order_by(Booking.slot_date.desc(), GymSlot.start_time.desc(), Booking.id.desc())
    )

    rows = list(db.execute(stmt).all())
    items: list[BookingItemResponse] = []
    for b, g, s in rows:
        if status_filter == "cancelled":
            if b.status != BookingStatus.CANCELLED.value:
                continue
        elif status_filter == "upcoming":
            if b.status == BookingStatus.CANCELLED.value:
                continue
            if b.slot_date < today:
                continue
        elif status_filter == "past":
            if b.status == BookingStatus.CANCELLED.value:
                continue
            # Past = scheduled date in past OR attendance marked.
            if not (b.slot_date < today or b.attendance_status is not None or b.status == BookingStatus.EXPIRED.value):
                continue
        elif status_filter and status_filter != "all":
            # Unknown filter -> treat as all.
            pass

        meta = _parse_notes(b.notes)
        access_type_id = meta.get("access_type_id")
        access_type = _access_type_label(access_type_id)

        class_name = None
        if access_type_id == "GROUP_CLASS":
            # MVP: use slot name as class name.
            class_name = s.name

        membership_covered = (str(b.total_price) == "0" or float(b.total_price) <= 0.0) and b.status == BookingStatus.CONFIRMED.value
        amount_paid = None
        if not membership_covered and float(b.total_price) > 0:
            amount_paid = str(b.total_price)

        loc_parts = [g.address_line_1, g.city]
        gym_location = ", ".join([p for p in loc_parts if p])

        # Booking status shown to user: attendance overrides.
        shown_status = b.status
        if b.status == BookingStatus.CONFIRMED.value and b.attendance_status == "ATTENDED":
            shown_status = "COMPLETED"
        elif b.status == BookingStatus.CONFIRMED.value and b.attendance_status == "NO_SHOW":
            shown_status = "MISSED"

        items.append(
            BookingItemResponse(
                booking_id=int(b.id),
                booking_status=shown_status,
                attendance_status=b.attendance_status,
                gym_id=int(g.id),
                gym_name=g.name,
                gym_location=gym_location,
                access_type=access_type,
                class_name=class_name,
                visit_date=b.slot_date,
                start_time=s.start_time,
                end_time=s.end_time,
                membership_covered=bool(membership_covered),
                amount_paid=amount_paid,
                currency=b.currency,
                booking_created_at=b.created_at,
                cancelled_at=b.cancelled_at,
            )
        )

    return items


@router.get("/activity", response_model=ProfileActivityResponse)
def get_profile_activity(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    uid = _require_user_id(db, current_user)

    stmt = select(Booking).where(Booking.user_id == uid).order_by(Booking.slot_date.desc())
    bookings = list(db.execute(stmt).scalars().all())

    attended = [b for b in bookings if b.attendance_status == "ATTENDED"]
    attended_dates = [b.slot_date for b in attended]
    streak = _compute_streak(attended_dates)

    partner_gyms = len({int(b.gym_id) for b in attended})

    # Breakdown by access_type_id stored in notes.
    counts: Counter[str] = Counter()
    class_attended = 0
    for b in attended:
        meta = _parse_notes(b.notes)
        at = meta.get("access_type_id") or "GYM_WORKOUT"
        counts[at] += 1
        if at == "GROUP_CLASS":
            class_attended += 1

    breakdown = []
    for k, c in counts.most_common():
        breakdown.append(
            {
                "key": k,
                "label": _access_type_label(k if k != "GYM_WORKOUT" else None),
                "count": int(c),
            }
        )

    return ProfileActivityResponse(
        total_gym_visits=len(attended),
        total_classes_attended=class_attended,
        current_streak_days=streak,
        partner_gyms_visited=partner_gyms,
        activity_breakdown=breakdown,
    )


@router.get("/favorites", response_model=FavoritesResponse)
def get_favorites(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    uid = _require_user_id(db, current_user)
    rows = list(
        db.execute(
            select(Gym.id, Gym.name, Gym.address_line_1, Gym.city, func.count(Booking.id))
            .join(Booking, Booking.gym_id == Gym.id)
            .where(Booking.user_id == uid, Booking.attendance_status == "ATTENDED")
            .group_by(Gym.id)
            .order_by(func.count(Booking.id).desc())
            .limit(3)
        ).all()
    )

    gyms = []
    for gid, name, a1, city, cnt in rows:
        gyms.append(
            {
                "gym_id": int(gid),
                "gym_name": name,
                "gym_location": ", ".join([p for p in [a1, city] if p]),
                "visit_count": int(cnt),
            }
        )
    return FavoritesResponse(gyms=gyms)


@router.get("/membership/pass", response_model=MembershipPassResponse)
def get_membership_pass(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    uid = _require_user_id(db, current_user)
    user = db.execute(select(User).where(User.id == uid)).scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    full_name = " ".join([p for p in [user.first_name, user.last_name] if p]) or "Member"
    now = datetime.utcnow()

    m = db.execute(select(UserMembership).where(UserMembership.user_id == uid).order_by(UserMembership.end_at.desc())).scalars().first()
    plan_name = None
    valid_until = None
    status_val = None
    if m:
        plan = db.execute(select(GymMembershipPlan).where(GymMembershipPlan.id == m.plan_id)).scalars().first()
        plan_name = plan.name if plan else None
        valid_until = m.end_at
        status_val = m.status

    active_memberships = list(
        db.execute(
            select(UserMembership).where(
                UserMembership.user_id == uid,
                UserMembership.status == MembershipStatus.ACTIVE.value,
                UserMembership.end_at > now,
            )
        )
        .scalars()
        .all()
    )
    active_gym_ids = [int(x.gym_id) for x in active_memberships]
    gym_access_count = len({int(x.gym_id) for x in active_memberships})

    membership_scope = None
    if gym_access_count == 1:
        membership_scope = "SINGLE_GYM"
    elif gym_access_count > 1:
        membership_scope = "MULTI_GYM"

    active_gyms: list[dict] = []
    if active_gym_ids:
        gyms = list(db.execute(select(Gym).where(Gym.id.in_(active_gym_ids))).scalars().all())
        gym_map = {int(g.id): g for g in gyms}
        for gid in active_gym_ids:
            g = gym_map.get(int(gid))
            if not g:
                continue
            active_gyms.append(
                {
                    "gym_id": int(g.id),
                    "gym_name": g.name,
                    "locality": g.address_line_2,
                    "city": g.city,
                }
            )

    visits_booked: int | None = None
    visits_completed: int | None = None
    if active_gym_ids and m:
        start_d = m.start_at.date() if m.start_at else None
        end_d = m.end_at.date() if m.end_at else None
        if start_d and end_d:
            visits_booked = int(
                db.execute(
                    select(func.count(Booking.id)).where(
                        Booking.user_id == uid,
                        Booking.gym_id.in_(active_gym_ids),
                        Booking.status == BookingStatus.CONFIRMED.value,
                        Booking.total_price <= 0,
                        Booking.slot_date >= start_d,
                        Booking.slot_date <= end_d,
                    )
                ).scalar_one()
                or 0
            )
            visits_completed = int(
                db.execute(
                    select(func.count(Booking.id)).where(
                        Booking.user_id == uid,
                        Booking.gym_id.in_(active_gym_ids),
                        Booking.status == BookingStatus.CONFIRMED.value,
                        Booking.total_price <= 0,
                        Booking.attendance_status == "ATTENDED",
                        Booking.slot_date >= start_d,
                        Booking.slot_date <= end_d,
                    )
                ).scalar_one()
                or 0
            )

    # Create a short-lived, opaque QR payload.
    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    qr_payload = jwt.encode(
        {"sub": str(uid), "type": "member_pass", "exp": exp, "membership_id": int(m.id) if m else None},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    return MembershipPassResponse(
        member_id=f"MBR-{uid:05d}",
        full_name=full_name,
        plan_name=plan_name,
        status=status_val,
        valid_until=valid_until,
        qr_payload=qr_payload,
        gym_access_count=int(gym_access_count or 0),
        membership_scope=membership_scope,
        active_gyms=active_gyms,
        visits_booked=visits_booked,
        visits_completed=visits_completed,
        pause_days_used=0,
        pause_days_remaining=60,
    )
