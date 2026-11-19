"""Validated geographic coordinates and index-friendly spherical search bounds."""
import math
from sqlalchemy import and_, case, func, or_

EARTH_KM = 6371.0088


def coordinates(latitude, longitude):
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    return lat, lon


def geographic_query(lat_column, lon_column, latitude, longitude, radius):
    """Bounding box first (including dateline/poles), then exact SQL haversine."""
    angle = radius / EARTH_KM
    delta = math.degrees(angle)
    south, north = max(-90, latitude - delta), min(90, latitude + delta)
    bounds = [lat_column.between(south, north), lon_column.between(-180, 180)]
    if south > -90 and north < 90:
        width = math.degrees(math.asin(min(1, math.sin(angle) / math.cos(math.radians(latitude)))))
        west, east = longitude - width, longitude + width
        if west < -180:
            bounds.append(or_(lon_column >= west + 360, lon_column <= east))
        elif east > 180:
            bounds.append(or_(lon_column >= west, lon_column <= east - 360))
        else:
            bounds.append(lon_column.between(west, east))
    a = (func.pow(func.sin(func.radians(lat_column - latitude) / 2), 2)
         + math.cos(math.radians(latitude)) * func.cos(func.radians(lat_column))
         * func.pow(func.sin(func.radians(lon_column - longitude) / 2), 2))
    clamped = case((a > 1, 1), (a < 0, 0), else_=a)
    distance = 2 * EARTH_KM * func.asin(func.sqrt(clamped))
    return and_(*bounds), distance