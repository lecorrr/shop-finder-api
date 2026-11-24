import pytest

from shops.models import Shop
from tests.factories import KYIV, ShopFactory

pytestmark = pytest.mark.django_db

SHOPS = "/api/v1/shops/"


def new_shop(**fields) -> dict:
    return {
        "name": "Corner Market",
        "address": "Test street 1",
        "latitude": 50.45,
        "longitude": 30.52,
    } | fields


def test_creating_a_shop_needs_a_login(api):
    assert api.post(SHOPS, new_shop(), format="json").status_code == 401


def test_the_creator_owns_the_shop(user_api, user):
    response = user_api.post(SHOPS, new_shop(), format="json")

    assert response.status_code == 201
    assert Shop.objects.get(pk=response.data["id"]).owner == user
    assert response.data["owner"] == user.username


def test_owner_cannot_be_set_by_the_client(user_api, user):
    other = ShopFactory().owner

    response = user_api.post(SHOPS, new_shop(owner=other.pk), format="json")

    assert Shop.objects.get(pk=response.data["id"]).owner == user


@pytest.mark.parametrize(
    "fields",
    [
        {"latitude": 91},
        {"latitude": -90.5},
        {"longitude": 180.5},
        {"name": ""},
        {"name": "x" * 121},
    ],
)
def test_invalid_shop_is_rejected(user_api, fields):
    response = user_api.post(SHOPS, new_shop(**fields), format="json")

    assert response.status_code == 400
    assert set(fields) <= set(response.data)


def test_only_the_owner_can_change_a_shop(user_api):
    foreign = ShopFactory()

    response = user_api.patch(f"{SHOPS}{foreign.pk}/", {"name": "Mine now"}, format="json")

    assert response.status_code == 404
    foreign.refresh_from_db()
    assert foreign.name != "Mine now"


def test_owner_updates_the_shop(user_api, user):
    shop = ShopFactory(owner=user)

    response = user_api.patch(f"{SHOPS}{shop.pk}/", {"opening_hours": "09-21"}, format="json")

    assert response.status_code == 200
    shop.refresh_from_db()
    assert shop.opening_hours == "09-21"


def test_deleting_closes_the_shop_and_hides_it(user_api, api, user):
    shop = ShopFactory(owner=user)

    deleted = user_api.delete(f"{SHOPS}{shop.pk}/")

    assert deleted.status_code == 204
    shop.refresh_from_db()
    assert not shop.is_active
    assert api.get(f"{SHOPS}{shop.pk}/").status_code == 404
    assert [row["id"] for row in user_api.get(f"{SHOPS}mine/").data["results"]] == [shop.pk]


def test_nearby_lists_shops_in_the_radius_nearest_first(api):
    far = ShopFactory.at(0, 1.9, name="far")
    near = ShopFactory.at(180, 0.4, name="near")
    ShopFactory.at(90, 2.5, name="outside")
    ShopFactory.at(270, 0.2, name="closed", is_active=False)

    response = api.get(SHOPS, {"lat": KYIV[0], "lon": KYIV[1], "radius_km": 2})

    assert [row["id"] for row in response.data["results"]] == [near.pk, far.pk]
    assert response.data["results"][0]["distance_km"] == pytest.approx(0.4, abs=0.01)


@pytest.mark.parametrize(
    "params",
    [
        {"lat": 50.45},  # lon missing
        {"lat": 91, "lon": 30},
        {"lat": 50, "lon": 30, "radius_km": 0},
        {"lat": 50, "lon": 30, "radius_km": 51},
        {"lat": "north", "lon": 30},
    ],
)
def test_invalid_nearby_query_is_rejected(api, params):
    assert api.get(SHOPS, params).status_code == 400


def test_name_filter(api):
    ShopFactory(name="Corner Market")
    ShopFactory(name="Night Shop")

    response = api.get(SHOPS, {"q": "corner"})

    assert [row["name"] for row in response.data["results"]] == ["Corner Market"]


def test_mine_needs_a_login_and_shows_only_own_shops(api, user_api, user):
    own = ShopFactory(owner=user)
    ShopFactory()

    assert api.get(f"{SHOPS}mine/").status_code == 401
    assert [row["id"] for row in user_api.get(f"{SHOPS}mine/").data["results"]] == [own.pk]


def test_list_is_paginated_without_extra_queries(api, django_assert_max_num_queries):
    for _ in range(25):
        ShopFactory()

    with django_assert_max_num_queries(2):  # count and page; owners are joined
        response = api.get(SHOPS, {"page_size": 10})

    assert response.data["count"] == 25
    assert len(response.data["results"]) == 10
