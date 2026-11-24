from decimal import Decimal

import pytest
from django.db import IntegrityError

from offers.models import Offer
from tests.factories import ShopFactory

pytestmark = pytest.mark.django_db


def offer_url(shop_id: int, product_id: str) -> str:
    return f"/api/v1/shops/{shop_id}/offers/{product_id}/"


def test_owner_sets_then_updates_an_offer(user_api, user, make_product):
    shop = ShopFactory(owner=user)
    product = make_product()

    created = user_api.put(offer_url(shop.pk, product["id"]), {"price": "49.90", "quantity": 3})
    updated = user_api.put(offer_url(shop.pk, product["id"]), {"price": "45.00", "quantity": 0})

    assert (created.status_code, updated.status_code) == (201, 200)
    offer = Offer.objects.get(shop=shop, product_id=product["id"])
    assert (offer.price, offer.quantity) == (Decimal("45.00"), 0)
    assert updated.data["product"]["name"] == product["name"]


def test_someone_elses_shop_is_404(user_api, make_product):
    shop = ShopFactory()

    response = user_api.put(offer_url(shop.pk, make_product()["id"]), {"price": "1", "quantity": 1})

    assert response.status_code == 404
    assert not Offer.objects.exists()


def test_offer_needs_a_login(api, make_product):
    shop = ShopFactory()

    response = api.put(offer_url(shop.pk, make_product()["id"]), {"price": "1", "quantity": 1})

    assert response.status_code == 401


def test_unknown_or_archived_product_is_rejected(user_api, user, make_product, products):
    shop = ShopFactory(owner=user)
    archived = make_product()
    products.archive(archived["id"])

    unknown = user_api.put(offer_url(shop.pk, "0" * 24), {"price": "1", "quantity": 1})
    retired = user_api.put(offer_url(shop.pk, archived["id"]), {"price": "1", "quantity": 1})

    assert (unknown.status_code, retired.status_code) == (400, 400)


@pytest.mark.parametrize(
    "body",
    [
        {"price": "0", "quantity": 1},
        {"price": "-5", "quantity": 1},
        {"price": "1.999", "quantity": 1},
        {"price": "1", "quantity": -1},
        {"price": "1"},
    ],
)
def test_invalid_offer_is_rejected(user_api, user, make_product, body):
    shop = ShopFactory(owner=user)

    response = user_api.put(offer_url(shop.pk, make_product()["id"]), body)

    assert response.status_code == 400


def test_owner_removes_an_offer(user_api, user, make_product):
    shop = ShopFactory(owner=user)
    product = make_product()
    Offer.objects.create(shop=shop, product_id=product["id"], price=10, quantity=1)

    first = user_api.delete(offer_url(shop.pk, product["id"]))
    again = user_api.delete(offer_url(shop.pk, product["id"]))

    assert (first.status_code, again.status_code) == (204, 404)


def test_shop_offers_are_listed_cheapest_first_with_their_products(api, make_product):
    shop = ShopFactory()
    for price in ["30.00", "10.00", "20.00"]:
        Offer.objects.create(shop=shop, product_id=make_product()["id"], price=price, quantity=1)

    response = api.get(f"/api/v1/shops/{shop.pk}/offers/")

    assert [row["price"] for row in response.data["results"]] == ["10.00", "20.00", "30.00"]
    assert all(row["product"]["name"] for row in response.data["results"])


def test_shop_offer_list_marks_archived_products(api, make_product, products):
    shop = ShopFactory()
    product = make_product()
    Offer.objects.create(shop=shop, product_id=product["id"], price=10, quantity=1)
    products.archive(product["id"])

    rows = api.get(f"/api/v1/shops/{shop.pk}/offers/").data["results"]

    assert rows[0]["product"]["status"] == "archived"


def test_database_refuses_a_second_offer_for_the_same_product(make_product):
    shop = ShopFactory()
    product_id = make_product()["id"]
    Offer.objects.create(shop=shop, product_id=product_id, price=1, quantity=1)

    with pytest.raises(IntegrityError):
        Offer.objects.create(shop=shop, product_id=product_id, price=2, quantity=1)
