from decimal import Decimal

import pytest
from pymongo.errors import ServerSelectionTimeoutError

from offers.models import Offer
from stats.repository import SearchEventRepository
from tests.factories import KYIV, ShopFactory

pytestmark = pytest.mark.django_db

SEARCH = "/api/v1/search/"


def search(api, **params):
    return api.get(SEARCH, {"lat": KYIV[0], "lon": KYIV[1], "radius_km": 2} | params)


def offer(shop, product, price="10.00", quantity=5) -> Offer:
    return Offer.objects.create(
        shop=shop, product_id=product["id"], price=Decimal(price), quantity=quantity
    )


def test_nearest_shop_first_then_cheapest(api, make_product):
    milk = make_product(name="Oat milk")
    far = ShopFactory.at(90, 1.5)
    pricey, cheap = ShopFactory.at(0, 0.3), ShopFactory.at(0, 0.3)  # same building
    offer(far, milk, "40.00")
    offer(pricey, milk, "60.00")
    offer(cheap, milk, "50.00")

    rows = search(api, q="oat milk").data["results"]

    assert [row["shop"]["id"] for row in rows] == [cheap.pk, pricey.pk, far.pk]
    assert rows[0]["product"]["name"] == "Oat milk"
    assert rows[0]["shop"]["distance_km"] == pytest.approx(0.3, abs=0.01)


def test_excludes_far_closed_and_sold_out_shops(api, make_product):
    milk = make_product(name="Oat milk")
    offer(ShopFactory.at(0, 2.5), milk)
    offer(ShopFactory.at(0, 0.5, is_active=False), milk)
    offer(ShopFactory.at(0, 0.5), milk, quantity=0)
    visible = ShopFactory.at(0, 1.9)
    offer(visible, milk)

    response = search(api, q="milk")

    assert [row["shop"]["id"] for row in response.data["results"]] == [visible.pk]


def test_only_matching_products(api, make_product):
    shop = ShopFactory()
    offer(shop, make_product(name="Oat milk"))
    offer(shop, make_product(name="Rye bread"))

    response = search(api, q="bread")

    assert [row["product"]["name"] for row in response.data["results"]] == ["Rye bread"]


def test_filters_by_category_attributes_and_price(api, make_product):
    shop = ShopFactory()
    small = make_product(name="Runner", category="shoes", attributes={"size_eu": 39})
    big = make_product(name="Runner", category="shoes", attributes={"size_eu": 42})
    offer(shop, small, "1000.00")
    offer(shop, big, "2500.00")
    offer(ShopFactory(), big, "3000.00")

    response = search(api, q="runner", category="shoes", **{"attr.size_eu": "42"}, max_price="2600")

    assert [row["price"] for row in response.data["results"]] == ["2500.00"]


@pytest.mark.parametrize(
    "params",
    [
        {"q": ""},
        {"q": "milk", "lat": 95},
        {"q": "milk", "radius_km": 0},
        {"q": "milk", "max_price": "0"},
        {"q": "milk", "attr.size_eu": "42"},
    ],
)
def test_invalid_search_is_rejected(api, params):
    assert search(api, **params).status_code == 400


def test_query_count_does_not_grow_with_results(api, make_product, django_assert_max_num_queries):
    products = [make_product(name=f"Oat milk {n}") for n in range(15)]
    for number, product in enumerate(products):
        offer(ShopFactory.at(number * 20, 0.1 + number / 10), product)

    with django_assert_max_num_queries(2):  # count and page, shops joined
        response = search(api, q="oat milk", page_size=15)

    assert response.data["count"] == 15


def test_every_search_is_logged_without_the_user_or_exact_place(user_api, mongo_db):
    search(user_api, q="  Oat   MILK ", lat=50.45678, lon=30.52345)

    event = mongo_db["search_events"].find_one()
    assert set(event) == {"_id", "q", "category", "location", "radius_km", "results", "created_at"}
    assert event["q"] == "oat milk"
    assert event["results"] == 0
    assert event["location"]["coordinates"] == [30.52, 50.46]


def test_search_works_when_logging_fails(api, make_product, monkeypatch):
    offer(ShopFactory(), make_product(name="Oat milk"))

    def broken_log(*args, **kwargs):
        raise ServerSelectionTimeoutError("no server")

    monkeypatch.setattr(SearchEventRepository, "log", broken_log)

    response = search(api, q="oat milk")

    assert response.status_code == 200
    assert response.data["count"] == 1
