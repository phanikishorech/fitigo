from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_db
from app.models.gym import Gym
from app.schemas.meta import LocationSuggestion


router = APIRouter(prefix="/meta")


@router.get("/app-links", response_model=dict)
def get_app_links():
    """Return app store links.

    These are intentionally configurable via environment variables so
    the frontend doesn't hardcode final URLs.
    """

    return {
        "android": settings.android_app_url,
        "ios": settings.ios_app_url,
    }


@router.get("/gym-types", response_model=list[str])
def list_gym_types():
    """Gym category list.

    MVP: static list served by backend (still backend-driven for frontend).
    Later: move to a DB table.
    """

    return [
        "All Gym Types",
        "General Fitness",
        "Strength Training",
        "Bodybuilding",
        "Cardio",
        "CrossFit",
        "Functional Training",
        "Yoga",
        "Pilates",
        "Swimming",
        "Dance Fitness",
        "Martial Arts",
        "Women's Fitness",
    ]


@router.get("/locations", response_model=list[LocationSuggestion])
def list_locations(
    db: Session = Depends(get_db),
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=30, ge=1, le=100),
):
    """Return location suggestions for the location picker.

    We currently derive locations from active, approved gyms in the DB.
    Each suggestion includes a representative latitude/longitude so the
    Nearby Gyms page can run geo discovery.

    NOTE: This is not a full geocoding/search service; it is an MVP
    to surface all localities/cities where we actually have gyms.
    """

    stmt = (
        select(
            Gym.address_line_2,
            Gym.city,
            Gym.state,
            Gym.country,
            Gym.latitude,
            Gym.longitude,
        )
        .where(and_(Gym.status == "APPROVED", Gym.is_active.is_(True)))
        .order_by(Gym.id.desc())
        .limit(2000)
    )

    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Gym.address_line_2.like(like),
                Gym.city.like(like),
                Gym.state.like(like),
            )
        )

    rows = list(db.execute(stmt).all())

    # Group by (location_name, city, state, country) and compute average lat/lon.
    agg: dict[tuple[str, str | None, str | None, str | None], dict] = {}
    for address_line_2, city, state, country, lat_s, lon_s in rows:
        # Prefer locality/address_line_2; fallback to city.
        loc_name = (address_line_2 or city or "").strip() if (address_line_2 or city) else ""
        if not loc_name:
            continue

        try:
            lat = float(lat_s) if lat_s is not None else None
            lon = float(lon_s) if lon_s is not None else None
        except Exception:
            lat = None
            lon = None

        # If gym row has no coords, it can't be used for discovery.
        if lat is None or lon is None:
            continue

        key = (loc_name, city, state, country)
        cur = agg.get(key)
        if not cur:
            cur = {"count": 0, "lat_sum": 0.0, "lon_sum": 0.0}
            agg[key] = cur
        cur["count"] += 1
        cur["lat_sum"] += lat
        cur["lon_sum"] += lon

    items: list[LocationSuggestion] = []
    for (loc_name, city, state, country), meta in agg.items():
        cnt = int(meta["count"] or 0)
        if cnt <= 0:
            continue
        items.append(
            LocationSuggestion(
                location_name=loc_name,
                latitude=meta["lat_sum"] / cnt,
                longitude=meta["lon_sum"] / cnt,
                city=city,
                state=state,
                country=country,
                gym_count=cnt,
            )
        )

    # Most useful ordering: more gyms first, then alphabetically.
    items.sort(key=lambda x: (-int(x.gym_count or 0), (x.location_name or "").lower()))

    return items[: int(limit)]
