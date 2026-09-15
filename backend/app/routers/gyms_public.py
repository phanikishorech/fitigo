from __future__ import annotations

from typing import Annotated

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.gym import Gym, GymFacility, GymFacilityMapping, GymImage, GymOperatingHours
from app.schemas.gym import GymDiscoverItem, GymDiscoverResponse, GymListItem, GymResponse
from app.schemas.gym_details import (
    GymAmenity,
    GymClassCard,
    GymDetailsImage,
    GymDetailsLocation,
    GymDetailsOpeningHours,
    GymDetailsOpeningHoursItem,
    GymDetailsRatings,
    GymDetailsResponse,
    GymMemberReview,
    GymMembershipAccess,
    GymWorkoutOption,
    RelatedGymItem,
)
from app.schemas.review import ReviewCreateRequest, ReviewResponse
from app.schemas.access_booking import (
    CreateAccessBookingRequest,
    CreateAccessBookingResponse,
    GymBookingOptionsResponse,
    ValidateBookingRequest,
    ValidateBookingResponse,
)
from app.schemas.operating_hours import OperatingHoursForDateResponse
from app.schemas.class_booking import ClassSessionPublicResponse
from app.models.class_booking import GymClass, ClassSession, ClassSessionStatus, GymSpecialHours
from app.services.review_service import ReviewService
from app.core.dependencies import get_optional_user, require_role
from app.core.roles import ROLE_CUSTOMER
from app.models.auth import User
from app.schemas.slot import GymSlotPublicResponse
from app.services.slot_service import SlotService
from app.models.membership import GymMembershipPlan, MembershipStatus, UserMembership
from app.models.review import GymReview, ReviewStatus
from app.models.slot import GymSlot, SlotAvailability
from app.models.booking import Payment
from app.services.booking_service import BookingService


router = APIRouter(prefix="/gyms")


def _format_time_range(open_time, close_time) -> str:
    if not open_time or not close_time:
        return "Closed"
    try:
        return f"{open_time.strftime('%I:%M %p').lstrip('0')} - {close_time.strftime('%I:%M %p').lstrip('0')}"
    except Exception:
        # Windows strftime edge cases
        return f"{open_time} - {close_time}"


def _operating_hours_for_date(db: Session, *, gym_id: int, dt: date) -> tuple[int, any, any, bool]:
    # special override
    sp = (
        db.execute(select(GymSpecialHours).where(GymSpecialHours.gym_id == gym_id, GymSpecialHours.date == dt))
        .scalars()
        .first()
    )
    if sp:
        dow = dt.weekday()  # 0=Mon
        return dow, sp.open_time, sp.close_time, bool(sp.is_closed)

    dow = dt.weekday()
    row = (
        db.execute(
            select(GymOperatingHours)
            .where(GymOperatingHours.gym_id == gym_id, GymOperatingHours.day_of_week == dow)
            .order_by(GymOperatingHours.id.desc())
        )
        .scalars()
        .first()
    )
    if not row:
        return dow, None, None, True
    return dow, row.open_time, row.close_time, bool(row.is_closed)


@router.get("/{gym_id}/operating-hours", response_model=OperatingHoursForDateResponse)
def get_operating_hours_for_date(
    gym_id: int,
    date_val: Annotated[date, Query(alias="date")],
    db: Session = Depends(get_db),
):
    gym = db.execute(select(Gym).where(Gym.id == gym_id, Gym.status == "APPROVED", Gym.is_active.is_(True))).scalars().first()
    if not gym:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

    dow, open_time, close_time, is_closed = _operating_hours_for_date(db, gym_id=int(gym.id), dt=date_val)
    label = "Closed" if is_closed else _format_time_range(open_time, close_time)
    return OperatingHoursForDateResponse(
        gym_id=int(gym.id),
        date=date_val,
        day_of_week=int(dow),
        open_time=open_time,
        close_time=close_time,
        is_closed=bool(is_closed),
        label=label,
    )


@router.get("/{gym_id}/class-sessions", response_model=list[ClassSessionPublicResponse])
def list_class_sessions_for_gym_and_date(
    gym_id: int,
    date_val: Annotated[date, Query(alias="date")],
    db: Session = Depends(get_db),
):
    gym = db.execute(select(Gym).where(Gym.id == gym_id, Gym.status == "APPROVED", Gym.is_active.is_(True))).scalars().first()
    if not gym:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")
    if not bool(getattr(gym, "has_classes", False)):
        return []

    rows = (
        db.execute(
            select(ClassSession, GymClass)
            .join(GymClass, GymClass.id == ClassSession.gym_class_id)
            .where(
                GymClass.gym_id == gym.id,
                GymClass.is_active.is_(True),
                ClassSession.session_date == date_val,
            )
            .order_by(ClassSession.start_time.asc())
        )
        .all()
    )

    out: list[ClassSessionPublicResponse] = []
    for sess, gclass in rows:
        max_cap = int(sess.maximum_capacity or 0)
        booked = int(sess.booked_capacity or 0)
        available = max(0, max_cap - booked)

        status_val = sess.status
        if status_val in {ClassSessionStatus.CANCELLED.value, ClassSessionStatus.CLOSED.value}:
            pass
        else:
            if available <= 0:
                status_val = ClassSessionStatus.FULL.value
            elif available <= 3:
                status_val = ClassSessionStatus.FEW_SLOTS_LEFT.value
            else:
                status_val = ClassSessionStatus.AVAILABLE.value

        out.append(
            ClassSessionPublicResponse(
                id=int(sess.id),
                gym_id=int(gclass.gym_id),
                class_id=int(gclass.id),
                class_name=gclass.class_name,
                class_date=sess.session_date,
                start_time=str(sess.start_time),
                end_time=str(sess.end_time),
                maximum_capacity=max_cap,
                booked_capacity=booked,
                available_capacity=available,
                price_per_person=str(sess.price_per_person),
                status=status_val,
            )
        )
    return out


def _get_dev_customer_id(db: Session) -> int | None:
    """Dev-only fallback for demo flows when the frontend isn't sending Authorization yet."""

    import os

    if os.getenv("ENVIRONMENT", "development") != "development":
        return None
    u = db.execute(select(User).where(User.email == "customer@example.com")).scalars().first()
    return int(u.id) if u else None


def _has_active_membership(db: Session, *, user_id: int, gym_id: int) -> bool:
    from datetime import datetime

    now = datetime.utcnow()
    return bool(
        db.execute(
            select(UserMembership.id).where(
                UserMembership.user_id == user_id,
                UserMembership.gym_id == gym_id,
                UserMembership.status == MembershipStatus.ACTIVE.value,
                UserMembership.end_at > now,
            )
        ).first()
    )


def _compute_membership_banner(status: str) -> dict:
    if status == "INCLUDED":
        return {
            "status": status,
            "title": "✓ Included in your membership",
            "subtitle": "You can access this gym at no additional cost.",
            "tone": "success",
        }
    if status == "UPGRADE_REQUIRED":
        return {
            "status": status,
            "title": "Upgrade required to access this gym",
            "subtitle": "Your current plan does not include this gym.",
            "tone": "warn",
        }
    if status == "DAY_PASS_AVAILABLE":
        return {
            "status": status,
            "title": "Day pass available from ₹299",
            "subtitle": "Get single-visit access without a membership.",
            "tone": "info",
        }
    return {
        "status": status,
        "title": "View membership plans to access",
        "subtitle": "Get access to this gym and other partner gyms with one membership.",
        "tone": "info",
    }


def _slugify(value: str) -> str:
    import re

    v = value.strip().lower()
    v = re.sub(r"[^a-z0-9]+", "-", v)
    v = re.sub(r"-+", "-", v).strip("-")
    return v or "gym"


def _haversine_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    import math

    r = 6371.0
    p = math.pi / 180.0
    dlat = (b_lat - a_lat) * p
    dlon = (b_lon - a_lon) * p
    x = math.sin(dlat / 2) ** 2 + math.cos(a_lat * p) * math.cos(b_lat * p) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))


def _fmt_time_ampm(t) -> str:
    """Format a time in a Windows-safe 12h format.

    Avoids `%-I` which is not supported on Windows and can raise
    `ValueError: Invalid format string`.
    """

    if t is None:
        return ""
    try:
        s = t.strftime("%I:%M %p")
        return s.lstrip("0")
    except Exception:
        return str(t)


def _to_public_gym_response(db: Session, gym: Gym) -> GymResponse:
    images = list(
        db.execute(select(GymImage).where(GymImage.gym_id == gym.id).order_by(GymImage.is_cover.desc(), GymImage.id.asc()))
        .scalars()
        .all()
    )

    facs = (
        db.execute(
            select(GymFacility)
            .join(GymFacilityMapping, GymFacilityMapping.facility_id == GymFacility.id)
            .where(GymFacilityMapping.gym_id == gym.id)
            .order_by(GymFacility.name.asc())
        )
        .scalars()
        .all()
    )

    hours = list(
        db.execute(select(GymOperatingHours).where(GymOperatingHours.gym_id == gym.id).order_by(GymOperatingHours.day_of_week.asc()))
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


@router.get("", response_model=list[GymListItem])
def list_public_gyms(
    db: Session = Depends(get_db),
    q: Annotated[str | None, Query(max_length=100)] = None,
    city: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    featured: Annotated[bool | None, Query()] = None,
    lat: Annotated[float | None, Query()] = None,
    lon: Annotated[float | None, Query()] = None,
    radius_km: Annotated[float | None, Query(ge=0.1, le=200.0)] = None,
):
    # Correlated subquery: pick one image file path per gym (prefer cover)
    cover_path_sq = (
        select(GymImage.file_path)
        .where(GymImage.gym_id == Gym.id)
        .order_by(GymImage.is_cover.desc(), GymImage.id.asc())
        .limit(1)
        .scalar_subquery()
    )

    filters = [Gym.status == "APPROVED", Gym.is_active.is_(True)]
    if q:
        like = f"%{q.strip()}%"
        filters.append(or_(Gym.name.like(like), Gym.description.like(like)))
    if city:
        filters.append(Gym.city == city)
    if featured is True:
        filters.append(Gym.is_featured.is_(True))

    # If doing geo filtering, we must NOT apply SQL limit/offset before distance filter,
    # otherwise we might end up with an empty page because the first N gyms have no coords.
    doing_geo = lat is not None and lon is not None

    if not doing_geo:
        stmt = (
            select(Gym, cover_path_sq.label("cover_path"))
            .where(and_(*filters))
            .order_by(Gym.id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list(db.execute(stmt).all())
        return [
            GymListItem(
                id=g.id,
                name=g.name,
                city=g.city,
                status=g.status,
                is_active=g.is_active,
                created_at=g.created_at,
                distance_km=None,
                cover_image_url=(f"/uploads/{cover_path}" if cover_path else None),
            )
            for g, cover_path in rows
        ]

    # Geo flow: fetch a bigger window, compute distance, filter, sort, then paginate.
    stmt = (
        select(Gym, cover_path_sq.label("cover_path"))
        .where(and_(*filters))
        .order_by(Gym.id.desc())
        .limit(500)
    )
    rows = list(db.execute(stmt).all())

    import math

    def _dist_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
        # haversine
        r = 6371.0
        p = math.pi / 180.0
        dlat = (b_lat - a_lat) * p
        dlon = (b_lon - a_lon) * p
        x = math.sin(dlat / 2) ** 2 + math.cos(a_lat * p) * math.cos(b_lat * p) * math.sin(dlon / 2) ** 2
        return 2 * r * math.asin(math.sqrt(x))

    gym_with_dist: list[tuple[Gym, float, str | None]] = []
    for g, cover_path in rows:
        if not g.latitude or not g.longitude:
            continue
        try:
            glat = float(g.latitude)
            glon = float(g.longitude)
        except ValueError:
            continue
        d = _dist_km(lat, lon, glat, glon)
        if radius_km is None or d <= radius_km:
            gym_with_dist.append((g, d, cover_path))

    gym_with_dist.sort(key=lambda t: t[1])
    page = gym_with_dist[offset : offset + limit]

    return [
        GymListItem(
            id=g.id,
            name=g.name,
            city=g.city,
            status=g.status,
            is_active=g.is_active,
            created_at=g.created_at,
            distance_km=d,
            cover_image_url=(f"/uploads/{cover_path}" if cover_path else None),
        )
        for g, d, cover_path in page
    ]


@router.get("/discover", response_model=GymDiscoverResponse)
def discover_gyms(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
    # Search/filter
    search: Annotated[str | None, Query(max_length=120)] = None,
    city: Annotated[str | None, Query(max_length=100)] = None,
    gym_type: Annotated[str | None, Query(max_length=80)] = None,
    facilities: Annotated[list[int] | None, Query()] = None,
    min_rating: Annotated[float | None, Query(ge=0, le=5)] = None,
    open_now: Annotated[bool | None, Query()] = None,
    membership_access: Annotated[str | None, Query(max_length=40)] = None,
    sort_by: Annotated[str | None, Query(max_length=40)] = None,
    # Geo
    latitude: Annotated[float | None, Query()] = None,
    longitude: Annotated[float | None, Query()] = None,
    radius_km: Annotated[float | None, Query(ge=0.1, le=200.0)] = 10.0,
    # Pagination
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=60)] = 12,
):
    """Discovery endpoint for the Nearby Gyms listing.

    Notes:
    - Distance is computed server-side (MVP uses haversine in Python).
    - Facility, rating, membership and open-now filters are applied server-side.
    - Returns pagination metadata + total_count for the listing header.
    """

    # Correlated subquery: pick one image file path per gym (prefer cover)
    cover_path_sq = (
        select(GymImage.file_path)
        .where(GymImage.gym_id == Gym.id)
        .order_by(GymImage.is_cover.desc(), GymImage.id.asc())
        .limit(1)
        .scalar_subquery()
    )

    filters = [Gym.status == "APPROVED", Gym.is_active.is_(True)]

    if search:
        like = f"%{search.strip()}%"
        filters.append(or_(Gym.name.like(like), Gym.description.like(like), Gym.address_line_1.like(like), Gym.address_line_2.like(like)))

    if city:
        filters.append(Gym.city == city)

    # MVP: gym_type is accepted for forward-compat but not yet stored on gyms table.
    _ = gym_type

    if facilities:
        gym_ids_sq = select(GymFacilityMapping.gym_id).where(GymFacilityMapping.facility_id.in_(facilities)).distinct()
        filters.append(Gym.id.in_(gym_ids_sq))

    # Fetch a bigger window first; we will apply distance/open/rating/membership filters in Python.
    stmt = (
        select(Gym, cover_path_sq.label("cover_path"))
        .where(and_(*filters))
        .order_by(Gym.is_featured.desc(), Gym.id.desc())
        .limit(700)
    )
    rows: list[tuple[Gym, str | None]] = list(db.execute(stmt).all())

    gyms = [g for g, _ in rows]
    gym_ids = [int(g.id) for g in gyms]
    if not gym_ids:
        return GymDiscoverResponse(total_count=0, page=page, page_size=page_size, has_more=False, gyms=[])

    # Ratings summary for the window
    rating_rows = list(
        db.execute(
            select(GymReview.gym_id, func.avg(GymReview.rating), func.count(GymReview.id))
            .where(GymReview.gym_id.in_(gym_ids), GymReview.status == ReviewStatus.PUBLISHED.value)
            .group_by(GymReview.gym_id)
        ).all()
    )
    rating_map: dict[int, tuple[float, int]] = {int(gid): (float(avg or 0), int(cnt or 0)) for gid, avg, cnt in rating_rows}

    # Facilities for window
    fac_rows = list(
        db.execute(
            select(GymFacilityMapping.gym_id, GymFacility)
            .join(GymFacility, GymFacility.id == GymFacilityMapping.facility_id)
            .where(GymFacilityMapping.gym_id.in_(gym_ids))
            .order_by(GymFacility.name.asc())
        ).all()
    )
    fac_map: dict[int, list[GymFacility]] = {}
    for gid, fac in fac_rows:
        fac_map.setdefault(int(gid), []).append(fac)

    # Open-now for window (today only)
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    # 0=Mon...6=Sun
    dow = int((now.weekday()) % 7)
    time_now = now.time()
    hours_rows = list(
        db.execute(
            select(GymOperatingHours)
            .where(GymOperatingHours.gym_id.in_(gym_ids), GymOperatingHours.day_of_week == dow)
        ).scalars().all()
    )
    hours_map: dict[int, GymOperatingHours] = {int(h.gym_id): h for h in hours_rows}

    def _is_open(gid: int) -> bool | None:
        h = hours_map.get(gid)
        if not h:
            return None
        if h.is_closed:
            return False
        if h.open_time is None or h.close_time is None:
            return None
        return bool(h.open_time <= time_now <= h.close_time)

    # Membership access (MVP): included if user has an active membership for this gym.
    included_gym_ids: set[int] = set()
    if current_user is not None:
        included_gym_ids = set(
            int(gid)
            for (gid,) in db.execute(
                select(UserMembership.gym_id)
                .where(
                    UserMembership.user_id == current_user.id,
                    UserMembership.status == MembershipStatus.ACTIVE.value,
                    UserMembership.end_at > now,
                )
                .distinct()
            ).all()
        )

    import math

    def _dist_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
        # haversine
        r = 6371.0
        p = math.pi / 180.0
        dlat = (b_lat - a_lat) * p
        dlon = (b_lon - a_lon) * p
        x = math.sin(dlat / 2) ** 2 + math.cos(a_lat * p) * math.cos(b_lat * p) * math.sin(dlon / 2) ** 2
        return 2 * r * math.asin(math.sqrt(x))

    doing_geo = latitude is not None and longitude is not None
    lat = float(latitude) if latitude is not None else None
    lon = float(longitude) if longitude is not None else None

    # Build enriched items and apply computed filters.
    enriched: list[GymDiscoverItem] = []
    for (g, cover_path) in rows:
        avg, cnt = rating_map.get(int(g.id), (0.0, 0))
        if min_rating is not None and cnt > 0 and avg < float(min_rating):
            continue
        if min_rating is not None and cnt == 0 and float(min_rating) > 0:
            continue

        dist_val: float | None = None
        if doing_geo:
            if not g.latitude or not g.longitude:
                continue
            try:
                glat = float(g.latitude)
                glon = float(g.longitude)
            except ValueError:
                continue
            dist_val = _dist_km(lat or 0, lon or 0, glat, glon)
            if radius_km is not None and dist_val > float(radius_km):
                continue

        is_open_now = _is_open(int(g.id))
        if open_now is True and is_open_now is not True:
            continue

        access_status = "INCLUDED" if int(g.id) in included_gym_ids else "NO_ACTIVE_MEMBERSHIP"
        if membership_access and access_status != membership_access:
            continue

        enriched.append(
            GymDiscoverItem(
                gym_id=int(g.id),
                gym_name=g.name,
                primary_image=(f"/uploads/{cover_path}" if cover_path else None),
                images=[],
                latitude=g.latitude,
                longitude=g.longitude,
                address=g.address_line_1,
                locality=g.address_line_2 or g.city,
                city=g.city,
                distance_km=dist_val,
                average_rating=(avg if cnt > 0 else None),
                review_count=cnt,
                facilities=[
                    {"id": f.id, "name": f.name, "description": f.description, "icon": f.icon}
                    for f in (fac_map.get(int(g.id)) or [])
                ],
                is_featured=bool(g.is_featured),
                membership_access_status=access_status,
                required_membership_tier=None,
                active_promotion=None,
                is_open_now=is_open_now,
            )
        )

    # Sorting
    def _membership_rank(status_val: str | None) -> int:
        if status_val == "INCLUDED":
            return 0
        if status_val == "DAY_PASS_AVAILABLE":
            return 1
        if status_val == "UPGRADE_REQUIRED":
            return 2
        if status_val == "NO_ACTIVE_MEMBERSHIP":
            return 3
        if status_val == "UNAVAILABLE":
            return 4
        return 5

    if sort_by == "rating":
        enriched.sort(key=lambda x: (x.average_rating is None, -(x.average_rating or 0), -(x.review_count or 0)))
    elif sort_by == "distance":
        enriched.sort(key=lambda x: (x.distance_km is None, x.distance_km or 1e9))
    else:
        # recommended
        enriched.sort(
            key=lambda x: (
                _membership_rank(x.membership_access_status),
                x.distance_km is None,
                x.distance_km or 1e9,
                x.average_rating is None,
                -(x.average_rating or 0),
                -(x.review_count or 0),
            )
        )

    total_count = len(enriched)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = enriched[start:end]
    has_more = end < total_count

    return GymDiscoverResponse(
        total_count=total_count,
        page=page,
        page_size=page_size,
        has_more=has_more,
        gyms=page_items,
    )


@router.get("/{gym_id}/reviews", response_model=list[ReviewResponse])
def list_gym_reviews(
    gym_id: int,
    db: Session = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    svc = ReviewService(db)
    items = svc.list_public_reviews(gym_id=gym_id, limit=limit, offset=offset)
    return [
        ReviewResponse(
            id=r.id,
            gym_id=r.gym_id,
            user_id=r.user_id,
            rating=r.rating,
            comment=r.comment,
            status=r.status,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in items
    ]


@router.post("/{gym_id}/reviews", response_model=ReviewResponse)
def create_gym_review(
    gym_id: int,
    payload: ReviewCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role({ROLE_CUSTOMER})),
):
    svc = ReviewService(db)
    r = svc.create_review(user_id=current_user.id, gym_id=gym_id, rating=payload.rating, comment=payload.comment)
    return ReviewResponse(
        id=r.id,
        gym_id=r.gym_id,
        user_id=r.user_id,
        rating=r.rating,
        comment=r.comment,
        status=r.status,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.get("/{gym_id}", response_model=GymResponse)
def get_public_gym(gym_id: int, db: Session = Depends(get_db)):
    gym = db.execute(
        select(Gym).where(Gym.id == gym_id, Gym.status == "APPROVED", Gym.is_active.is_(True))
    ).scalars().first()
    if not gym:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")
    return _to_public_gym_response(db, gym)


@router.get("/{gym_id}/details", response_model=GymDetailsResponse)
def get_gym_details(
    gym_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    """Gym details endpoint for Screen 4 (Gym Details Page)."""

    from datetime import datetime as dt

    # Gym
    gym = db.execute(
        select(Gym).where(Gym.id == gym_id, Gym.status == "APPROVED", Gym.is_active.is_(True))
    ).scalars().first()
    if not gym:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

    # Images
    imgs = list(
        db.execute(
            select(GymImage)
            .where(GymImage.gym_id == gym.id)
            .order_by(GymImage.is_cover.desc(), GymImage.display_order.asc(), GymImage.id.asc())
        )
        .scalars()
        .all()
    )
    images = [
        GymDetailsImage(
            image_id=int(i.id),
            image_url=f"/uploads/{i.file_path}",
            alt_text=i.original_filename or gym.name,
            display_order=int(i.display_order or 0),
        )
        for i in imgs
    ]

    # Facilities
    facs = (
        db.execute(
            select(GymFacility)
            .join(GymFacilityMapping, GymFacilityMapping.facility_id == GymFacility.id)
            .where(GymFacilityMapping.gym_id == gym.id)
            .order_by(GymFacility.name.asc())
        )
        .scalars()
        .all()
    )

    # Opening hours
    hours_rows = list(
        db.execute(
            select(GymOperatingHours)
            .where(GymOperatingHours.gym_id == gym.id)
            .order_by(GymOperatingHours.day_of_week.asc())
        )
        .scalars()
        .all()
    )
    weekly = [
        GymDetailsOpeningHoursItem(
            day_of_week=int(h.day_of_week),
            open_time=h.open_time,
            close_time=h.close_time,
            is_closed=bool(h.is_closed),
        )
        for h in hours_rows
    ]

    now = dt.utcnow()
    dow = int((now.weekday()) % 7)
    hours_today = next((h for h in hours_rows if int(h.day_of_week) == dow), None)
    open_now: bool | None = None
    open_today: str | None = None
    if hours_today is not None:
        if bool(hours_today.is_closed):
            open_now = False
            open_today = "Closed"
        elif hours_today.open_time is not None and hours_today.close_time is not None:
            t = now.time()
            open_now = bool(hours_today.open_time <= t <= hours_today.close_time)
            open_today = f"{_fmt_time_ampm(hours_today.open_time)} - {_fmt_time_ampm(hours_today.close_time)}"

    # If strftime %-I isn't supported on Windows, fallback to default formatting.
    opening_hours = GymDetailsOpeningHours(open_now=open_now, open_today=open_today, weekly=weekly)

    # Ratings summary
    avg_cnt = db.execute(
        select(func.avg(GymReview.rating), func.count(GymReview.id)).where(
            GymReview.gym_id == gym.id,
            GymReview.status == ReviewStatus.PUBLISHED.value,
        )
    ).first()
    avg_rating = float(avg_cnt[0] or 0)
    review_count = int(avg_cnt[1] or 0)
    average_rating_val = avg_rating if review_count > 0 else None

    user_rating: int | None = None
    if current_user is not None:
        ur = db.execute(
            select(GymReview.rating).where(
                GymReview.gym_id == gym.id,
                GymReview.user_id == current_user.id,
            )
        ).first()
        if ur and ur[0] is not None:
            user_rating = int(ur[0])

    ratings = GymDetailsRatings(
        average_rating=average_rating_val,
        review_count=review_count,
        user_rating=user_rating,
    )

    # Membership access (MVP): included if user has an active membership for this gym.
    included = False
    current_plan_name: str | None = None
    if current_user is not None:
        active_m = (
            db.execute(
                select(UserMembership)
                .where(
                    UserMembership.user_id == current_user.id,
                    UserMembership.gym_id == gym.id,
                    UserMembership.status == MembershipStatus.ACTIVE.value,
                    UserMembership.end_at > now,
                )
                .order_by(UserMembership.end_at.desc())
            )
            .scalars()
            .first()
        )
        included = bool(active_m)
        if active_m is not None:
            plan = db.execute(select(GymMembershipPlan).where(GymMembershipPlan.id == active_m.plan_id)).scalars().first()
            current_plan_name = plan.name if plan else None
    access_status = "INCLUDED" if included else "NO_ACTIVE_MEMBERSHIP"
    membership_access = GymMembershipAccess(
        status=access_status,
        current_plan=current_plan_name,
        required_plan=None,
        upgrade_required=False,
        day_pass_available=False,
        day_pass_price=None,
    )

    # Split workout options vs amenities from facilities.
    workout_names = {"Cardio", "Strength", "Yoga"}
    workout_options: list[GymWorkoutOption] = []
    amenities: list[GymAmenity] = []
    for f in facs:
        if f.name in workout_names:
            workout_options.append(
                GymWorkoutOption(
                    workout_type_id=int(f.id),
                    workout_type_name=f.name,
                    icon=f.icon,
                    access_type="INCLUDED" if access_status == "INCLUDED" else "MEMBERSHIP_REQUIRED",
                    additional_fee=None,
                    membership_requirement=None,
                )
            )
        else:
            amenities.append(GymAmenity(amenity_id=int(f.id), amenity_name=f.name, icon=f.icon))

    # Description + policies (MVP fallback)
    description = gym.description
    if not description:
        description = (
            "A partner gym on Fitigo with modern equipment, clean facilities, and smooth check-ins. "
            "Explore workout options, opening hours, photos, and member reviews before you visit."
        )

    rules = [
        "Valid membership or access pass required.",
        "Check-in is mandatory before entering.",
        "Proper workout attire is required.",
        "Please re-rack weights and wipe equipment after use.",
        "Outside trainers may require prior approval.",
    ]

    important_information = [
        "Bring a government ID for first-time verification if requested.",
        "Peak hours may be crowded; consider visiting early mornings.",
    ]

    # Location
    full_address = ", ".join(
        [
            p
            for p in [
                gym.address_line_1,
                gym.address_line_2,
                gym.city,
                gym.state,
                gym.postal_code,
                gym.country,
            ]
            if p
        ]
    )
    lat_f = float(gym.latitude) if gym.latitude else None
    lon_f = float(gym.longitude) if gym.longitude else None
    location = GymDetailsLocation(
        locality=gym.address_line_2,
        city=gym.city,
        state=gym.state,
        country=gym.country,
        full_address=full_address or None,
        latitude=lat_f,
        longitude=lon_f,
    )

    # Classes nearby (MVP): use today's slots as class cards.
    classes_nearby: list[GymClassCard] = []
    today = now.date()
    slot_rows = list(
        db.execute(
            select(GymSlot, SlotAvailability)
            .join(SlotAvailability, SlotAvailability.gym_slot_id == GymSlot.id)
            .where(GymSlot.gym_id == gym.id, GymSlot.is_active == 1, SlotAvailability.slot_date == today)
            .order_by(GymSlot.start_time.asc())
        ).all()
    )
    for s, av in slot_rows[:6]:
        cap_total = int(av.capacity_override or s.capacity or 0)
        booked = int(av.booked_count or 0)
        remaining = max(0, cap_total - booked - int(av.blocked_count or 0))
        status_badge = "FULL" if remaining <= 0 else "AVAILABLE"
        start_at = dt.combine(today, s.start_time)
        end_at = dt.combine(today, s.end_time)
        classes_nearby.append(
            GymClassCard(
                class_id=int(s.id),
                kind="GROUP CLASS",
                status=status_badge,
                title=s.name,
                gym_name=gym.name,
                start_at=start_at,
                end_at=end_at,
                level="Beginner",
                filled=booked,
                capacity=cap_total,
            )
        )

    # Reviews (latest 3)
    review_rows = list(
        db.execute(
            select(GymReview, User)
            .join(User, User.id == GymReview.user_id)
            .where(GymReview.gym_id == gym.id, GymReview.status == ReviewStatus.PUBLISHED.value)
            .order_by(GymReview.created_at.desc())
            .limit(3)
        ).all()
    )
    reviews = [
        GymMemberReview(
            review_id=int(r.id),
            user_display_name=(u.first_name or (u.email.split("@")[0] if u.email else "Member")),
            rating=int(r.rating),
            comment=r.comment,
            created_at=r.created_at,
        )
        for r, u in review_rows
    ]

    # Related gyms (within ~6km, same city, exclude current)
    related_gyms: list[RelatedGymItem] = []
    if lat_f is not None and lon_f is not None:
        # correlated subquery for cover
        cover_path_sq = (
            select(GymImage.file_path)
            .where(GymImage.gym_id == Gym.id)
            .order_by(GymImage.is_cover.desc(), GymImage.id.asc())
            .limit(1)
            .scalar_subquery()
        )
        rel_rows = list(
            db.execute(
                select(Gym, cover_path_sq.label("cover_path"))
                .where(
                    Gym.id != gym.id,
                    Gym.status == "APPROVED",
                    Gym.is_active.is_(True),
                    Gym.city == gym.city,
                )
                .order_by(Gym.is_featured.desc(), Gym.id.desc())
                .limit(40)
            ).all()
        )

        # precompute ratings for related gyms
        rel_ids = [int(g.id) for g, _ in rel_rows]
        rating_rows = []
        if rel_ids:
            rating_rows = list(
                db.execute(
                    select(GymReview.gym_id, func.avg(GymReview.rating), func.count(GymReview.id))
                    .where(GymReview.gym_id.in_(rel_ids), GymReview.status == ReviewStatus.PUBLISHED.value)
                    .group_by(GymReview.gym_id)
                ).all()
            )
        rating_map: dict[int, tuple[float, int]] = {int(gid): (float(avg or 0), int(cnt or 0)) for gid, avg, cnt in rating_rows}

        included_ids: set[int] = set()
        if current_user is not None and rel_ids:
            included_ids = set(
                int(r[0])
                for r in db.execute(
                    select(UserMembership.gym_id)
                    .where(
                        UserMembership.user_id == current_user.id,
                        UserMembership.status == MembershipStatus.ACTIVE.value,
                        UserMembership.end_at > now,
                        UserMembership.gym_id.in_(rel_ids),
                    )
                    .distinct()
                ).all()
            )

        for rg, cover_path in rel_rows:
            if not rg.latitude or not rg.longitude:
                continue
            try:
                rlat = float(rg.latitude)
                rlon = float(rg.longitude)
            except ValueError:
                continue
            d = _haversine_km(lat_f, lon_f, rlat, rlon)
            if d > 6.0:
                continue
            avg, cnt = rating_map.get(int(rg.id), (0.0, 0))
            related_gyms.append(
                RelatedGymItem(
                    gym_id=int(rg.id),
                    gym_name=rg.name,
                    primary_image=(f"/uploads/{cover_path}" if cover_path else None),
                    locality=rg.address_line_2 or rg.city,
                    city=rg.city,
                    distance_km=float(d),
                    average_rating=(float(avg) if int(cnt) > 0 else None),
                    review_count=int(cnt or 0),
                    membership_access_status=("INCLUDED" if int(rg.id) in included_ids else "NO_ACTIVE_MEMBERSHIP"),
                )
            )
        related_gyms.sort(key=lambda x: (x.distance_km is None, x.distance_km or 1e9))
        related_gyms = related_gyms[:8]

    return GymDetailsResponse(
        gym_id=int(gym.id),
        gym_name=gym.name,
        slug=_slugify(gym.name),
        location=location,
        ratings=ratings,
        images=images,
        opening_hours=opening_hours,
        workout_options=workout_options,
        amenities=amenities,
        description=description,
        important_information=important_information,
        rules=rules,
        membership_access=membership_access,
        classes_nearby=classes_nearby,
        related_gyms=related_gyms,
        reviews=reviews,
        reviews_summary={
            "average_rating": average_rating_val,
            "review_count": review_count,
        },
    )


@router.get("/{gym_id}/booking-options", response_model=GymBookingOptionsResponse)
def get_gym_booking_options(
    gym_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    gym = db.execute(select(Gym).where(Gym.id == gym_id, Gym.status == "APPROVED", Gym.is_active.is_(True))).scalars().first()
    if not gym:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

    user_id: int | None = int(current_user.id) if current_user else _get_dev_customer_id(db)
    included = _has_active_membership(db, user_id=user_id, gym_id=int(gym.id)) if user_id is not None else False
    membership_status = "INCLUDED" if included else "NO_ACTIVE_MEMBERSHIP"

    banner = _compute_membership_banner(membership_status)

    from datetime import datetime

    now = datetime.utcnow()

    # Access types derived from facilities (MVP)
    facs = (
        db.execute(
            select(GymFacility)
            .join(GymFacilityMapping, GymFacilityMapping.facility_id == GymFacility.id)
            .where(GymFacilityMapping.gym_id == gym.id)
        )
        .scalars()
        .all()
    )
    has_yoga = any(f.name == "Yoga" for f in facs)
    has_strength = any(f.name == "Strength" for f in facs)
    has_cardio = any(f.name == "Cardio" for f in facs)

    options = [
        {
            "id": "GYM_WORKOUT",
            "name": "Gym Workout",
            "type": "WORKOUT",
            "icon": "🏋️",
            "membership_included": included,
            "additional_price": None if included else "From slot price",
        },
    ]
    if has_yoga:
        options.append(
            {
                "id": "YOGA_SESSION",
                "name": "Yoga Session",
                "type": "WORKOUT",
                "icon": "🧘",
                "membership_included": included,
                "additional_price": None if included else "From slot price",
            }
        )
    if has_strength:
        options.append(
            {
                "id": "STRENGTH_TRAINING",
                "name": "Strength Training",
                "type": "WORKOUT",
                "icon": "🏋️",
                "membership_included": included,
                "additional_price": None if included else "From slot price",
            }
        )
    if has_cardio:
        options.append(
            {
                "id": "CARDIO",
                "name": "Cardio",
                "type": "WORKOUT",
                "icon": "❤️",
                "membership_included": included,
                "additional_price": None if included else "From slot price",
            }
        )
    # Use slots as classes (MVP)
    options.append(
        {
            "id": "GROUP_CLASS",
            "name": "Group Class",
            "type": "CLASS",
            "icon": "👥",
            "membership_included": included,
            "additional_price": None if included else "From slot price",
        }
    )
    # Day pass (MVP)
    options.append(
        {
            "id": "DAY_PASS",
            "name": "Day Pass",
            "type": "DAY_PASS",
            "icon": "🎟️",
            "membership_included": False,
            "additional_price": "299.00",
        }
    )

    workout_areas = [
        {"id": "MAIN_FLOOR", "name": "Main Gym Floor"},
        {"id": "STRENGTH", "name": "Strength Area"},
        {"id": "CARDIO", "name": "Cardio Area"},
        {"id": "FUNCTIONAL", "name": "Functional Training Zone"},
        {"id": "STUDIO", "name": "Studio"},
    ]

    # Classes availability (new booking model)
    has_active_class_sessions = False
    if bool(getattr(gym, "has_classes", False)):
        today = now.date()
        has_active_class_sessions = bool(
            db.execute(
                select(ClassSession.id)
                .join(GymClass, GymClass.id == ClassSession.gym_class_id)
                .where(
                    GymClass.gym_id == gym.id,
                    GymClass.is_active.is_(True),
                    ClassSession.session_date >= today,
                    ClassSession.status.notin_([ClassSessionStatus.CANCELLED.value, ClassSessionStatus.CLOSED.value]),
                )
                .limit(1)
            ).first()
        )

    # Keep backward compatible fields but also include pricing/features for the new Add-to-Cart page.
    resp = GymBookingOptionsResponse(
        gym_id=int(gym.id),
        gym_name=gym.name,
        locality=gym.address_line_2,
        city=gym.city,
        membership_status=banner,
        available_access_types=options,
        workout_areas=workout_areas,
        gym_price_per_person=str(getattr(gym, "gym_price_per_person", 0) or 0),
        has_classes=bool(getattr(gym, "has_classes", False)),
        classes_available=bool(has_active_class_sessions),
        classes_unavailable_message=None if has_active_class_sessions else "Classes are not available at this gym.",
    )
    return resp


@router.post("/{gym_id}/validate-booking", response_model=ValidateBookingResponse)
def validate_gym_booking(
    gym_id: int,
    payload: ValidateBookingRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    """Validate availability + compute pricing. Pricing is authoritative."""

    from decimal import Decimal
    from datetime import datetime

    gym = db.execute(select(Gym).where(Gym.id == gym_id, Gym.status == "APPROVED", Gym.is_active.is_(True))).scalars().first()
    if not gym:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

    slot = db.execute(select(GymSlot).where(GymSlot.id == payload.gym_slot_id, GymSlot.is_active == 1)).scalars().first()
    if not slot or int(slot.gym_id) != int(gym.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slot not found")

    # Ensure SlotAvailability exists
    av = (
        db.execute(
            select(SlotAvailability).where(
                SlotAvailability.gym_slot_id == slot.id,
                SlotAvailability.slot_date == payload.slot_date,
            )
        )
        .scalars()
        .first()
    )
    if not av:
        av = SlotAvailability(
            gym_slot_id=slot.id,
            slot_date=payload.slot_date,
            capacity_override=None,
            booked_count=0,
            blocked_count=0,
            status="AVAILABLE",
        )
        db.add(av)
        db.commit()

    cap_total = int(av.capacity_override if av.capacity_override is not None else slot.capacity)
    remaining = cap_total - int(av.booked_count) - int(av.blocked_count)
    if remaining < int(payload.quantity):
        return ValidateBookingResponse(
            available=False,
            availability_message="This time is unavailable. Please choose another time.",
            membership_eligible=False,
            currency="INR",
            price="0.00",
            discount="0.00",
            tax="0.00",
            total="0.00",
        )

    # Membership eligibility
    user_id: int | None = int(current_user.id) if current_user else _get_dev_customer_id(db)
    included = _has_active_membership(db, user_id=user_id, gym_id=int(gym.id)) if user_id is not None else False

    # Pricing
    currency = "INR"
    base = Decimal("0")
    if payload.access_type_id == "DAY_PASS":
        base = Decimal("299.00")
        included_for_item = False
    else:
        base = Decimal(str(slot.price))
        included_for_item = included

    total = Decimal("0") if included_for_item else (base * Decimal(int(payload.quantity)))

    msg = "✓ Available for your selected time"
    if remaining <= 3:
        msg = f"⚠ Only {remaining} spots remaining"

    return ValidateBookingResponse(
        available=True,
        availability_message=msg,
        membership_eligible=included_for_item,
        currency=currency,
        price=str(base.quantize(Decimal('0.01'))),
        discount="0.00",
        tax="0.00",
        total=str(total.quantize(Decimal('0.01'))),
    )


@router.post("/{gym_id}/access-bookings", response_model=CreateAccessBookingResponse)
def create_access_bookings(
    gym_id: int,
    payload: CreateAccessBookingRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    """Create one or more visit bookings and (for free bookings) auto-confirm.

    This exists to support membership-covered visits (₹0) while still using the existing
    Booking model.
    """

    from decimal import Decimal

    gym = db.execute(select(Gym).where(Gym.id == gym_id, Gym.status == "APPROVED", Gym.is_active.is_(True))).scalars().first()
    if not gym:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gym not found")

    user_id: int | None = int(current_user.id) if current_user else _get_dev_customer_id(db)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    results = []
    svc = BookingService(db)
    for item in payload.items:
        validated = validate_gym_booking(gym_id=gym_id, payload=item, db=db, current_user=current_user)
        if not validated.available:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=validated.availability_message)

        total = Decimal(str(validated.total))

        # Override unit price when the access type price differs from slot price (e.g. DAY_PASS)
        unit_price_override = None
        if item.access_type_id == "DAY_PASS":
            unit_price_override = Decimal(str(validated.price))
        elif total <= Decimal("0"):
            unit_price_override = Decimal("0")

        # Store context in notes (MVP)
        notes_parts = [
            f"access_type_id={item.access_type_id}",
            f"workout_area_id={item.workout_area_id}" if item.workout_area_id else None,
            f"duration_minutes={item.duration_minutes}" if item.duration_minutes else None,
            payload.notes,
        ]
        notes = "\n".join([p for p in notes_parts if p])

        booking = svc.create_booking(
            user_id=user_id,
            gym_slot_id=item.gym_slot_id,
            slot_date=item.slot_date,
            quantity=item.quantity,
            notes=notes,
            unit_price_override=unit_price_override,
            auto_confirm_if_free=True,
        )

        # Re-load payment for response
        payment = db.execute(select(Payment).where(Payment.booking_id == booking.id)).scalars().first()
        results.append(
            {
                "booking_id": int(booking.id),
                "status": booking.status,
                "payment_status": payment.status if payment else None,
                "total": str(booking.total_price),
                "currency": booking.currency,
            }
        )

    return CreateAccessBookingResponse(results=results)


@router.get("/{gym_id}/slots", response_model=list[GymSlotPublicResponse])
def get_public_gym_slots(
    gym_id: int,
    slot_date: Annotated[date, Query(alias="date")],
    db: Session = Depends(get_db),
):
    svc = SlotService(db)
    pairs = svc.list_public_slots(gym_id=gym_id, slot_date=slot_date)

    out: list[GymSlotPublicResponse] = []
    for slot, av in pairs:
        cap_total = av.capacity_override if av.capacity_override is not None else slot.capacity
        remaining = cap_total - av.booked_count - av.blocked_count
        if remaining < 0:
            remaining = 0

        # Derive FULL if counts exceed
        status_val = av.status
        if status_val == "AVAILABLE" and remaining == 0:
            status_val = "FULL"

        out.append(
            GymSlotPublicResponse(
                id=slot.id,
                gym_id=slot.gym_id,
                name=slot.name,
                start_time=slot.start_time,
                end_time=slot.end_time,
                capacity=slot.capacity,
                price=str(slot.price),
                is_active=bool(slot.is_active),
                availability={
                    "slot_date": av.slot_date,
                    "status": status_val,
                    "capacity_total": cap_total,
                    "booked_count": av.booked_count,
                    "blocked_count": av.blocked_count,
                    "remaining_capacity": remaining,
                },
            )
        )
    return out
