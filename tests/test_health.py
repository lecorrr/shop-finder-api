import pytest
from rest_framework.throttling import AnonRateThrottle

from core import checks

pytestmark = pytest.mark.django_db

HEALTH = "/api/v1/health/"


def test_healthy(api):
    response = api.get(HEALTH)

    assert response.status_code == 200
    assert response.data["checks"] == {"postgres": "ok", "mongo": "ok", "redis": "ok"}
    assert response.data["version"]


def test_a_broken_dependency_makes_it_503_and_names_it(api, monkeypatch):
    def mongo_down():
        raise TimeoutError("no server")

    monkeypatch.setitem(checks.CHECKS, "mongo", mongo_down)

    response = api.get(HEALTH)

    assert response.status_code == 503
    assert response.data["checks"]["mongo"] == "error"
    assert response.data["checks"]["postgres"] == "ok"
    assert "no server" not in str(response.data)  # details go to the log, not the internet


def test_health_is_not_throttled(api, monkeypatch):
    monkeypatch.setitem(AnonRateThrottle.THROTTLE_RATES, "anon", "1/min")

    codes = {api.get(HEALTH).status_code for _ in range(3)}

    assert codes == {200}
