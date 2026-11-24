"""Distances on the Earth's surface, in Python and as a database expression.

Kilometres throughout; latitude and longitude in degrees (WGS 84, as phones report them).
The bounding box does not wrap around the 180th meridian, which no Ukrainian shop is near.
"""

import math
from dataclasses import dataclass

from django.db.models import Expression, F, FloatField, Value
from django.db.models.functions import ASin, Cos, Least, Power, Radians, Sin, Sqrt

EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class BoundingBox:
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


def bounding_box(lat: float, lon: float, radius_km: float) -> BoundingBox:
    """The smallest box that contains the whole circle, on the same sphere as distance_km().

    Used to let an index cut the candidates first, so it must never be smaller than the
    circle: a shop inside the radius but outside the box would silently go missing.
    """
    angle = radius_km / EARTH_RADIUS_KM  # radians along the surface
    phi = math.radians(lat)
    min_lat = max(lat - math.degrees(angle), -90.0)
    max_lat = min(lat + math.degrees(angle), 90.0)
    if phi + angle >= math.pi / 2 or phi - angle <= -math.pi / 2:
        # The circle covers a pole, so it spans every longitude.
        return BoundingBox(min_lat, max_lat, -180.0, 180.0)
    # Widest point of the circle in longitude (the circle is not widest at its own latitude).
    dlon = math.degrees(math.asin(math.sin(angle) / math.cos(phi)))
    return BoundingBox(min_lat, max_lat, max(lon - dlon, -180.0), min(lon + dlon, 180.0))


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance by the haversine formula."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def distance_expression(lat: float, lon: float, lat_field: str, lon_field: str) -> Expression:
    """The same haversine formula as a SQL expression, for annotate() and order_by()."""

    def number(value: float) -> Value:
        return Value(value, output_field=FloatField())

    phi1 = Radians(number(lat))
    phi2 = Radians(F(lat_field))
    dphi = Radians(F(lat_field) - number(lat))
    dlambda = Radians(F(lon_field) - number(lon))
    a = Power(Sin(dphi / 2), 2) + Cos(phi1) * Cos(phi2) * Power(Sin(dlambda / 2), 2)
    # Rounding can push sqrt(a) a hair above 1, and asin() of that is an error in Postgres.
    return number(2 * EARTH_RADIUS_KM) * ASin(
        Least(Sqrt(a), number(1.0)), output_field=FloatField()
    )
