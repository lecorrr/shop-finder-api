import itertools

import pytest
from django.conf import settings
from django.core.cache import cache
from rest_framework.test import APIClient

from catalog import repository as catalog_repository
from catalog.barcodes import with_check_digit
from catalog.repository import ProductRepository, to_api
from shopfinder import mongo
from stats import repository as stats_repository
from tests.factories import UserFactory


@pytest.fixture(scope="session")
def mongo_db():
    assert settings.MONGO_DB.endswith("_test"), "tests must never touch a real database"
    mongo.client().drop_database(settings.MONGO_DB)
    db = mongo.database()
    catalog_repository.ensure_schema(db)
    stats_repository.ensure_schema(db, settings.SEARCH_EVENTS_KEEP_DAYS)
    yield db
    mongo.client().drop_database(settings.MONGO_DB)


@pytest.fixture(autouse=True)
def clean_state(mongo_db):
    """Throttle counters live in the cache and documents in MongoDB; neither may leak."""
    cache.clear()
    yield
    for name in mongo_db.list_collection_names():
        mongo_db[name].delete_many({})


@pytest.fixture
def products(mongo_db) -> ProductRepository:
    return ProductRepository(mongo_db)


@pytest.fixture
def make_product(products):
    numbers = itertools.count(1)

    def make(**fields) -> dict:
        number = next(numbers)
        data = {
            "name": f"Product {number}",
            "brand": "Test brand",
            "category": "food",
            "barcode": with_check_digit(f"200{number:09d}"),
            "attributes": {},
            "tags": [],
        } | fields
        return to_api(products.create(data))

    return make


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def user_api(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def staff_api(db) -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(is_staff=True))
    return client
