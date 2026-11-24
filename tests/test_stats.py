from datetime import UTC, datetime, timedelta

import pytest

from stats import repository as stats_repository
from stats.repository import TTL_INDEX, SearchEventRepository
from tests.factories import KYIV, point_at

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
MOST_WANTED = "/api/v1/stats/most-wanted/"


@pytest.fixture
def events(mongo_db) -> SearchEventRepository:
    return SearchEventRepository(mongo_db)


def searched(events, q, *, times=1, results=1, where=KYIV, days_ago=0):
    for _ in range(times):
        events.log(
            q=q,
            category=None,
            lat=where[0],
            lon=where[1],
            radius_km=2,
            results=results,
            now=NOW - timedelta(days=days_ago),
        )


def most_wanted(events, **options):
    defaults = {"lat": KYIV[0], "lon": KYIV[1], "radius_km": 5, "days": 7, "now": NOW}
    return events.most_wanted(**(defaults | options))


def test_counts_searches_and_the_ones_that_found_nothing(events):
    searched(events, "oat milk", times=4)
    searched(events, "kombucha", times=2, results=0)
    searched(events, "kombucha", times=1, results=4)

    rows = most_wanted(events)

    assert [(row["query"], row["searches"], row["unmet"]) for row in rows] == [
        ("oat milk", 4, 0),
        ("kombucha", 3, 2),
    ]


def test_only_searches_near_the_point_and_in_the_period(events):
    searched(events, "near and recent")
    searched(events, "far away", where=point_at(0, 8))
    searched(events, "too old", days_ago=8)

    assert [row["query"] for row in most_wanted(events)] == ["near and recent"]


def test_unmet_only(events):
    searched(events, "oat milk", times=5)
    searched(events, "kombucha", results=0)

    assert [row["query"] for row in most_wanted(events, unmet_only=True)] == ["kombucha"]


def test_queries_are_normalised_before_counting(events):
    searched(events, "Oat Milk")
    searched(events, "  oat   milk")

    assert most_wanted(events)[0]["searches"] == 2


def test_limit(events):
    for number in range(5):
        searched(events, f"query {number}")

    assert len(most_wanted(events, limit=3)) == 3


def test_retention_index_follows_the_setting(mongo_db):
    stats_repository.ensure_schema(mongo_db, keep_days=30)
    seconds = mongo_db["search_events"].index_information()[TTL_INDEX]["expireAfterSeconds"]
    stats_repository.ensure_schema(mongo_db, keep_days=180)  # back to the test default

    assert seconds == 30 * 24 * 3600


@pytest.mark.django_db
def test_endpoint_is_for_logged_in_users(api, user_api, events):
    searched(events, "kombucha", results=0, days_ago=0)
    params = {"lat": KYIV[0], "lon": KYIV[1], "days": 30}

    assert api.get(MOST_WANTED, params).status_code == 401
    response = user_api.get(MOST_WANTED, params | {"unmet": "true"})
    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize(
    "params",
    [{"lat": 50}, {"lat": 50, "lon": 30, "days": 0}, {"lat": 50, "lon": 30, "limit": 51}],
)
def test_invalid_query_is_rejected(user_api, params):
    assert user_api.get(MOST_WANTED, params).status_code == 400
