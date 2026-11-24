import pytest
from pymongo.errors import WriteError

pytestmark = pytest.mark.django_db

PRODUCTS = "/api/v1/products/"


def new_product(**fields) -> dict:
    return {
        "name": "Oat milk",
        "brand": "Green Field",
        "category": "drinks",
        "barcode": "4006381333931",
        "attributes": {"volume_l": 1},
        "tags": ["Milk", " oat ", "milk"],
    } | fields


def test_staff_creates_a_product(staff_api):
    response = staff_api.post(PRODUCTS, new_product(), format="json")

    assert response.status_code == 201
    assert response.data["status"] == "active"
    assert response.data["tags"] == ["milk", "oat"]
    assert len(response.data["id"]) == 24


@pytest.mark.parametrize("client, code", [("api", 401), ("user_api", 403)])
def test_only_staff_write_the_catalogue(request, client, code):
    response = request.getfixturevalue(client).post(PRODUCTS, new_product(), format="json")

    assert response.status_code == code


@pytest.mark.parametrize(
    "fields, field",
    [
        ({"barcode": "4006381333932"}, "barcode"),
        ({"category": "toys"}, "category"),
        ({"attributes": {"volume_l": 1, "size_eu": 42}}, "attributes"),
        ({"attributes": {}}, "attributes"),  # drinks need a volume
        ({"tags": [f"tag{n}" for n in range(21)]}, "tags"),
        ({"name": ""}, "name"),
    ],
)
def test_invalid_product_is_rejected(staff_api, fields, field):
    response = staff_api.post(PRODUCTS, new_product(**fields), format="json")

    assert response.status_code == 400
    assert field in response.data


def test_barcode_is_unique(staff_api):
    staff_api.post(PRODUCTS, new_product(), format="json")

    response = staff_api.post(PRODUCTS, new_product(name="Copy"), format="json")

    assert response.status_code == 400
    assert "barcode" in response.data


def test_products_without_barcode_do_not_clash(staff_api):
    codes = [
        staff_api.post(
            PRODUCTS, new_product(name=f"Loose {n}", barcode=""), format="json"
        ).status_code
        for n in range(2)
    ]

    assert codes == [201, 201]


def test_mongodb_validator_rejects_what_the_api_would_never_write(products):
    with pytest.raises(WriteError):
        products.products.insert_one({"name": "no category or status"})


def test_search_needs_every_word(api, make_product):
    make_product(name="Oat milk", tags=["vegan"])
    make_product(name="Cow milk")
    make_product(name="Oat flakes")

    response = api.get(PRODUCTS, {"q": "milk OAT"})

    assert [row["name"] for row in response.data["results"]] == ["Oat milk"]


def test_search_finds_tags_and_brands(api, make_product):
    make_product(name="Oat drink", brand="Green Field", tags=["milk"])

    assert api.get(PRODUCTS, {"q": "milk"}).data["count"] == 1
    assert api.get(PRODUCTS, {"q": "green"}).data["count"] == 1


def test_search_handles_ukrainian_words_and_apostrophes(api, make_product):
    make_product(name="М’ясо куряче", tags=["м'ясо"])

    assert api.get(PRODUCTS, {"q": "м’ясо"}).data["count"] == 1
    assert api.get(PRODUCTS, {"q": "КУРЯЧЕ"}).data["count"] == 1


def test_attribute_filter(api, make_product):
    make_product(name="Runner", category="shoes", attributes={"size_eu": 42})
    make_product(name="Runner", category="shoes", attributes={"size_eu": 43})

    response = api.get(PRODUCTS, {"category": "shoes", "attr.size_eu": "42"})

    assert [row["attributes"]["size_eu"] for row in response.data["results"]] == [42]


@pytest.mark.parametrize(
    "params",
    [
        {"attr.size_eu": "42"},  # needs a category
        {"category": "shoes", "attr.weight_g": "5"},
        {"category": "shoes", "attr.size_eu": "big"},
        {"page": 0},
        {"page_size": 101},
    ],
)
def test_invalid_list_query_is_rejected(api, params):
    assert api.get(PRODUCTS, params).status_code == 400


def test_list_pages(api, make_product):
    for number in range(5):
        make_product(name=f"Item {number}")

    first = api.get(PRODUCTS, {"page_size": 2})
    last = api.get(PRODUCTS, {"page_size": 2, "page": 3})

    assert first.data["count"] == 5
    assert [row["name"] for row in first.data["results"]] == ["Item 0", "Item 1"]
    assert "page=2" in first.data["next"]
    assert first.data["previous"] is None
    assert [row["name"] for row in last.data["results"]] == ["Item 4"]
    assert last.data["next"] is None


def test_patch_validates_the_merged_product(staff_api, make_product):
    product = make_product(category="drinks", attributes={"volume_l": 1})

    changed_category = staff_api.patch(
        f"{PRODUCTS}{product['id']}/", {"category": "shoes"}, format="json"
    )
    renamed = staff_api.patch(f"{PRODUCTS}{product['id']}/", {"name": "Renamed"}, format="json")

    assert changed_category.status_code == 400  # volume_l is not a shoe attribute
    assert renamed.status_code == 200
    assert renamed.data["attributes"] == {"volume_l": 1}


def test_patch_can_remove_the_barcode(staff_api, make_product, products):
    product = make_product()

    response = staff_api.patch(f"{PRODUCTS}{product['id']}/", {"barcode": ""}, format="json")

    assert response.data["barcode"] is None
    assert "barcode" not in products.get(product["id"])


def test_patch_rejects_a_barcode_taken_by_another_product(staff_api, make_product):
    first = make_product()
    second = make_product()

    response = staff_api.patch(
        f"{PRODUCTS}{second['id']}/", {"barcode": first["barcode"]}, format="json"
    )

    assert response.status_code == 400


def test_delete_archives_and_hides_the_product(staff_api, api, make_product):
    product = make_product(name="Old stock")

    assert staff_api.delete(f"{PRODUCTS}{product['id']}/").status_code == 204
    assert api.get(f"{PRODUCTS}{product['id']}/").status_code == 404
    assert api.get(PRODUCTS, {"q": "old stock"}).data["count"] == 0
    assert staff_api.get(f"{PRODUCTS}{product['id']}/").data["status"] == "archived"


@pytest.mark.parametrize("product_id", ["0" * 24, "not-an-object-id", "A" * 24])
def test_unknown_product_is_404(api, product_id):
    assert api.get(f"{PRODUCTS}{product_id}/").status_code == 404
