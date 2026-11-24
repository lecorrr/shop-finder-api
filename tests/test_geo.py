import pytest

from shops.geo import bounding_box, distance_expression, distance_km
from shops.models import Shop
from tests.factories import KYIV, ShopFactory, point_at

LVIV = (49.8397, 24.0297)


def test_distance_kyiv_to_lviv():
    assert distance_km(*KYIV, *LVIV) == pytest.approx(467.5, abs=0.5)


def test_distance_to_the_same_point_is_zero():
    assert distance_km(*KYIV, *KYIV) == 0


@pytest.mark.parametrize("lat", [0.0, 50.45, -33.9, 70.0, 89.0])
@pytest.mark.parametrize("radius_km", [0.1, 2, 50])
def test_bounding_box_contains_the_whole_circle(lat, radius_km):
    origin = (lat, 30.0)
    box = bounding_box(*origin, radius_km)
    for bearing in range(0, 360, 5):
        point_lat, point_lon = point_at(bearing, radius_km * 0.9999, origin)
        assert box.min_lat <= point_lat <= box.max_lat
        assert box.min_lon <= point_lon <= box.max_lon


def test_bounding_box_spans_all_longitudes_around_a_pole():
    box = bounding_box(89.99, 30.0, 5)
    assert (box.min_lon, box.max_lon, box.max_lat) == (-180.0, 180.0, 90.0)


@pytest.mark.django_db
def test_database_distance_matches_python():
    for bearing, distance in [(0, 0.5), (90, 3), (200, 12.5)]:
        ShopFactory.at(bearing, distance)
    rows = Shop.objects.annotate(
        distance_km=distance_expression(*KYIV, "latitude", "longitude")
    ).values_list("latitude", "longitude", "distance_km")
    for lat, lon, database_km in rows:
        assert database_km == pytest.approx(distance_km(*KYIV, lat, lon), rel=1e-9)
