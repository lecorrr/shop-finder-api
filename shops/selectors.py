from django.db.models import QuerySet

from shops.geo import bounding_box, distance_expression
from shops.models import Shop


def shops_near(lat: float, lon: float, radius_km: float) -> QuerySet[Shop]:
    """Active shops within radius_km, nearest first, each annotated with distance_km.

    The bounding box lets the (latitude, longitude) index cut the candidates before the
    exact distance is computed for the few rows left.
    """
    box = bounding_box(lat, lon, radius_km)
    return (
        Shop.objects.filter(
            is_active=True,
            latitude__range=(box.min_lat, box.max_lat),
            longitude__range=(box.min_lon, box.max_lon),
        )
        .annotate(distance_km=distance_expression(lat, lon, "latitude", "longitude"))
        .filter(distance_km__lte=radius_km)
        .order_by("distance_km", "id")
    )
