"""Customer discovery: database filtering/count/order/page before enrichment."""
from fastapi import HTTPException
from sqlalchemy import case, func, literal, or_, select
from app.core.time import ist_now
from app.models.gym import Gym, GymImage, GymFacility, GymFacilityMapping, GymOperatingHours
from app.models.review import GymReview, ReviewStatus
from app.schemas.gym import GymDiscoverItem, GymDiscoverResponse
from app.services.gym_geo import coordinates, geographic_query
from app.services.membership_entitlement import included_ids


def discover(db, user, *, search, city, facilities, min_rating, open_now, membership_access,
             sort_by, latitude, longitude, radius_km, page, page_size):
    if (latitude is None) != (longitude is None):
        raise HTTPException(422, 'Latitude and longitude must be provided together.')
    filters = [Gym.status == 'APPROVED', Gym.is_active.is_(True)]
    distance = literal(None)
    if latitude is not None:
        if coordinates(latitude, longitude) is None:
            raise HTTPException(422, 'Invalid discovery coordinates.')
        bounds, distance = geographic_query(Gym.geo_latitude, Gym.geo_longitude, latitude, longitude, radius_km or 10)
        filters.extend([bounds, distance <= (radius_km or 10)])
    if search and search.strip():
        term = f'%{search.strip()}%'
        filters.append(or_(*(column.like(term) for column in
                            [Gym.name, Gym.description, Gym.address_line_1, Gym.address_line_2])))
    if city:
        filters.append(Gym.city == city)
    if facilities:
        filters.append(Gym.id.in_(select(GymFacilityMapping.gym_id).where(GymFacilityMapping.facility_id.in_(facilities))))
    rating = (select(GymReview.gym_id.label('gid'), func.avg(GymReview.rating).label('average'),
                     func.count(GymReview.id).label('count')).where(GymReview.status == ReviewStatus.PUBLISHED.value)
              .group_by(GymReview.gym_id).subquery())
    now = ist_now()
    opened = (select(GymOperatingHours.gym_id).where(
        GymOperatingHours.gym_id == Gym.id, GymOperatingHours.day_of_week == now.weekday(),
        GymOperatingHours.is_closed.is_(False), GymOperatingHours.open_time <= now.time(),
        GymOperatingHours.close_time >= now.time()).exists())
    if min_rating is not None:
        filters.append(func.coalesce(rating.c.average, 0) >= min_rating)
    if open_now:
        filters.append(opened)
    member_ids = included_ids(db, user.id, now) if user else set()
    included = Gym.id.in_(member_ids)
    if membership_access == 'INCLUDED':
        filters.append(included)
    elif membership_access == 'NO_ACTIVE_MEMBERSHIP':
        filters.append(~included)
    elif membership_access:
        filters.append(literal(False))
    base = select(Gym.id).outerjoin(rating, rating.c.gid == Gym.id).where(*filters)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    cover = (select(GymImage.file_path).where(GymImage.gym_id == Gym.id)
             .order_by(GymImage.is_cover.desc(), GymImage.id).limit(1).scalar_subquery())
    if sort_by == 'rating':
        order = [func.coalesce(rating.c.average, 0).desc(), func.coalesce(rating.c.count, 0).desc()]
    elif sort_by == 'distance' and latitude is not None:
        order = [distance]
    else:
        order = [case((included, 0), else_=1), Gym.is_featured.desc()]
        if latitude is not None:
            order.append(distance)
        order.append(func.coalesce(rating.c.average, 0).desc())
    rows = db.execute(select(Gym, cover, distance, rating.c.average, rating.c.count)
                      .outerjoin(rating, rating.c.gid == Gym.id).where(*filters)
                      .order_by(*order, Gym.id).offset((page - 1) * page_size).limit(page_size)).all()
    ids = [g.id for g, *_ in rows]
    fac_map = {}
    if ids:
        for gid, fac in db.execute(select(GymFacilityMapping.gym_id, GymFacility)
                                  .join(GymFacility, GymFacility.id == GymFacilityMapping.facility_id)
                                  .where(GymFacilityMapping.gym_id.in_(ids)).order_by(GymFacility.name)):
            fac_map.setdefault(gid, []).append(dict(id=fac.id, name=fac.name, description=fac.description, icon=fac.icon))
    hours = {h.gym_id: h for h in db.scalars(select(GymOperatingHours).where(
        GymOperatingHours.gym_id.in_(ids), GymOperatingHours.day_of_week == now.weekday()))} if ids else {}
    items = []
    for gym, image, dist, avg, count in rows:
        h = hours.get(gym.id)
        is_open = None if not h else bool(not h.is_closed and h.open_time and h.close_time and h.open_time <= now.time() <= h.close_time)
        items.append(GymDiscoverItem(
            gym_id=gym.id, gym_name=gym.name, latitude=gym.latitude, longitude=gym.longitude,
            address=', '.join(p for p in [gym.address_line_1, gym.address_line_2, gym.city, gym.state] if p),
            locality=gym.address_line_2 or gym.city, city=gym.city, distance_km=dist,
            primary_image=f'/uploads/{image}' if image else None, average_rating=float(avg) if avg is not None else None,
            review_count=count or 0, facilities=fac_map.get(gym.id, []), is_featured=gym.is_featured,
            membership_access_status='INCLUDED' if gym.id in member_ids else 'NO_ACTIVE_MEMBERSHIP',
            is_open_now=is_open, starting_price=str(gym.gym_price_per_person), is_active=gym.is_active))
    return GymDiscoverResponse(total_count=total, page=page, page_size=page_size,
                               has_more=page * page_size < total, gyms=items)