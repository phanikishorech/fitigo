from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_optional_user, require_role
from app.core.roles import ROLE_CUSTOMER
from app.core.time import utc_today
from app.services.access_service import AccessService
from app.services.membership_entitlement import membership_name, included_ids, scope, active_memberships as resolve_memberships, covers
from app.models.access import Checkin
from app.database.session import get_db
from app.models.auth import User
from app.models.booking import Booking, BookingStatus
from app.models.gym import Gym
from app.models.membership import GymMembershipPlan, MembershipDailyAccess, MembershipStatus, UserMembership
from app.models.slot import GymSlot
from app.schemas.profile import (
    BookingItemResponse,
    FavoritesResponse,
    MembershipPassResponse,
    MembershipSummaryResponse,
    ProfileActivityResponse,
    ProfileResponse,
)
from app.schemas.membership_access import MembershipCalendarResponse, MembershipDailyQRResponse


router = APIRouter(prefix="/profile")


def _month_bounds(yyyymm: str) -> tuple[date, date]:
    """Return inclusive month start/end (date) for a YYYY-MM string."""

    parts = (yyyymm or "").split("-")
    if len(parts) != 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid month format; expected YYYY-MM")
    try:
        y, m = int(parts[0]), int(parts[1])
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid month format; expected YYYY-MM")
    if not 2000 <= y <= 2100 or not 1 <= m <= 12:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid month format; expected YYYY-MM")
    start = date(y, m, 1)
    # compute last day
    if m == 12:
        end = date(y + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(y, m + 1, 1) - timedelta(days=1)
    return start, end


@router.get("/membership/calendar", response_model=MembershipCalendarResponse, deprecated=True)
def get_membership_calendar(
    gym_id: int = Query(..., ge=1),
    month: str | None = Query(default=None, max_length=7, description="YYYY-MM"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_CUSTOMER})),
):
    uid = _require_user_id(db, current_user)
    now = datetime.utcnow()

    gym = db.get(Gym, gym_id)
    m = next((item for item in resolve_memberships(db, uid, now) if gym and covers([item], gym)), None)
    if not m:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active membership for this gym")

    # default month = current month (UTC)
    month_val = month or f"{now.year:04d}-{now.month:02d}"
    month_start, month_end = _month_bounds(month_val)

    calendar = AccessService(db).calendar_month(user_id=uid, year=month_start.year, month=month_start.month)
    accessed_dates = [day["date"] for day in calendar["days"] if day.get("qr_status") == "USED" and day.get("gym_id") == gym_id]

    return MembershipCalendarResponse(
        gym_id=int(gym_id),
        membership_start=m.start_at,
        membership_end=m.end_at,
        month=month_val,
        month_start=month_start,
        month_end=month_end,
        accessed_dates=accessed_dates,
    )


@router.get("/membership/daily-qr", response_model=MembershipDailyQRResponse, deprecated=True)
def get_membership_daily_qr(
    response: Response,
    gym_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_CUSTOMER})),
):
    """Compatibility adapter. Only the central access service issues credentials."""
    response.headers["Cache-Control"] = "no-store"
    svc = AccessService(db)
    ctx = svc._resolve_today_access_context(user_id=current_user.id)
    gym = db.get(Gym, gym_id)
    if not gym or not covers(resolve_memberships(db, current_user.id, datetime.utcnow()), gym):
        raise HTTPException(status_code=403, detail={"code": "GYM_NOT_ELIGIBLE"})
    if ctx.get("gym_id") is not None and ctx["gym_id"] != gym_id:
        raise HTTPException(status_code=403, detail="No active membership for this gym")
    result = svc.get_today_access(user_id=current_user.id)
    return MembershipDailyQRResponse(
        gym_id=gym_id, access_date=utc_today(), status=result["status"],
        scanned=result["status"] == "USED", scanned_at=result.get("used_at"),
        qr_payload=result.get("qr_token"), expires_at=result.get("expires_at"),
    )


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

    active_memberships = resolve_memberships(db, uid, now)

    m = active_memberships[0] if active_memberships else (
        db.execute(select(UserMembership).where(UserMembership.user_id == uid).order_by(UserMembership.end_at.desc())).scalars().first()
    )

    plan_name = None
    if m:
        plan_name = membership_name(db, m)

    membership_scope = scope(active_memberships)

    # Gym details for active memberships
    active_gym_ids = sorted(included_ids(db, uid, now))
    gym_access_count = len(active_gym_ids)
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
    pause_days_max = 0
    pause_days_used = 0
    pause_days_remaining = pause_days_max

    return MembershipSummaryResponse(
        membership_id=int(m.id) if m else None,
        plan_name=plan_name,
        status=("EXPIRED" if m and m.status == "ACTIVE" and m.end_at <= now else m.status if m else None),
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

    # Include membership QR scans as visit items (shown under Past/All).
    # NOTE: These are not "bookings" in the bookings table, but they represent
    # an actual gym access via membership daily QR.
    if status_filter in {"past", "all", None, ""}:
        scan_stmt = (
            select(MembershipDailyAccess, Gym)
            .join(Gym, Gym.id == MembershipDailyAccess.gym_id)
            .where(
                MembershipDailyAccess.user_id == uid,
                MembershipDailyAccess.status == "SCANNED",
            )
        )
        if status_filter == "past":
            scan_stmt = scan_stmt.where(MembershipDailyAccess.access_date <= today)

        scan_rows = list(db.execute(scan_stmt).all())
        for rec, g in scan_rows:
            loc_parts = [g.address_line_1, g.city]
            gym_location = ", ".join([p for p in loc_parts if p])
            scanned_at = rec.scanned_at or rec.created_at
            if scanned_at:
                dt = scanned_at
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                t = dt.time().replace(tzinfo=None)
            else:
                t = time(0, 0, 0)

            # Use negative IDs to avoid colliding with real booking IDs.
            # Frontend can treat booking_id < 0 as a membership-scan visit.
            items.append(
                BookingItemResponse(
                    booking_id=-2 * int(rec.id),
                    booking_status="COMPLETED",
                    attendance_status="ATTENDED",
                    gym_id=int(g.id),
                    gym_name=g.name,
                    gym_location=gym_location,
                    access_type="Membership Scan",
                    class_name=None,
                    visit_date=rec.access_date,
                    start_time=t,
                    end_time=t,
                    membership_covered=True,
                    amount_paid=None,
                    currency="INR",
                    booking_created_at=scanned_at,
                    cancelled_at=None,
                )
            )

    if status_filter in {"past", "all", None, ""}:
        rows = db.execute(select(Checkin, Gym).join(Gym, Gym.id == Checkin.gym_id).where(
            Checkin.user_id == uid, Checkin.status == "SUCCESS",
        )).all()
        for checkin, gym in rows:
            dt = checkin.checkin_time
            items.append(BookingItemResponse(
                booking_id=-(2 * int(checkin.id) + 1), booking_status="COMPLETED",
                attendance_status="ATTENDED", gym_id=int(gym.id), gym_name=gym.name,
                gym_location=", ".join(p for p in [gym.address_line_1, gym.city] if p),
                access_type="Membership Scan", class_name=None, visit_date=dt.date(),
                start_time=dt.time(), end_time=dt.time(), membership_covered=True,
                amount_paid=None, currency="INR", booking_created_at=dt, cancelled_at=None,
            ))

    # Keep newest first.
    items.sort(key=lambda x: (x.visit_date, x.start_time, x.booking_id), reverse=True)

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
        plan_name = membership_name(db, m)
        valid_until = m.end_at
        status_val = m.status

    active_memberships = resolve_memberships(db, uid, now)
    active_gym_ids = sorted(included_ids(db, uid, now))
    gym_access_count = len(active_gym_ids)
    membership_scope = scope(active_memberships)

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

    # Pass metadata is not a credential; daily QR issuance has one authority.
    qr_payload = None

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
        pause_days_remaining=0,
    )
