import math

import factory

from shops.geo import EARTH_RADIUS_KM
from shops.models import Shop

KYIV = (50.4501, 30.5234)


def point_at(bearing_deg: float, distance_km: float, origin=KYIV) -> tuple[float, float]:
    """The point distance_km away from origin in the given direction (0 is north)."""
    phi1, lambda1, theta = map(math.radians, (origin[0], origin[1], bearing_deg))
    angle = distance_km / EARTH_RADIUS_KM
    phi2 = math.asin(
        math.sin(phi1) * math.cos(angle) + math.cos(phi1) * math.sin(angle) * math.cos(theta)
    )
    lambda2 = lambda1 + math.atan2(
        math.sin(theta) * math.sin(angle) * math.cos(phi1),
        math.cos(angle) - math.sin(phi1) * math.sin(phi2),
    )
    return math.degrees(phi2), math.degrees(lambda2)


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "accounts.User"

    username = factory.Sequence(lambda number: f"user{number}")
    email = factory.LazyAttribute(lambda user: f"{user.username}@example.com")
    password = factory.django.Password("test-pass-123")


class ShopFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Shop

    owner = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda number: f"Shop {number}")
    address = "Test street 1, Kyiv"
    latitude = KYIV[0]
    longitude = KYIV[1]

    @classmethod
    def at(cls, bearing_deg: float, distance_km: float, **fields) -> Shop:
        latitude, longitude = point_at(bearing_deg, distance_km)
        return cls(latitude=latitude, longitude=longitude, **fields)
