import pytest
from rest_framework.throttling import ScopedRateThrottle

from accounts.models import User
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

REGISTER = "/api/v1/auth/register/"


def registration(**fields) -> dict:
    return {
        "username": "olena",
        "email": "olena@example.com",
        "password": "a-long-pass-42",
    } | fields


def test_register_creates_a_user_with_a_hashed_password(api):
    response = api.post(REGISTER, registration(), format="json")

    assert response.status_code == 201
    assert "password" not in response.data
    user = User.objects.get(username="olena")
    assert user.check_password("a-long-pass-42")
    assert user.password != "a-long-pass-42"


@pytest.mark.parametrize(
    "password",
    [
        "short1",  # too short
        "12345678901",  # only digits
        "password123",  # a common password
        "olena2026",  # too close to the user name
    ],
)
def test_register_rejects_weak_passwords(api, password):
    response = api.post(REGISTER, registration(password=password), format="json")

    assert response.status_code == 400
    assert "password" in response.data


def test_register_rejects_an_email_already_used_in_another_case(api):
    UserFactory(email="olena@example.com")

    response = api.post(REGISTER, registration(email="Olena@Example.com"), format="json")

    assert response.status_code == 400
    assert "email" in response.data


def test_register_is_throttled(api, monkeypatch):
    # DRF copies the rates into the throttle class at import, so patch them there.
    monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "register", "2/hour")

    codes = [
        api.post(
            REGISTER, registration(username=f"user{n}", email=f"user{n}@example.com")
        ).status_code
        for n in range(3)
    ]

    assert codes == [201, 201, 429]


def test_token_pair_and_refresh(api):
    UserFactory(username="taras", password="test-pass-123")

    tokens = api.post(
        "/api/v1/auth/token/", {"username": "taras", "password": "test-pass-123"}, format="json"
    )
    refreshed = api.post("/api/v1/auth/token/refresh/", {"refresh": tokens.data["refresh"]})

    assert tokens.status_code == 200
    assert refreshed.status_code == 200
    assert refreshed.data["access"]


def test_bearer_token_authenticates_requests(api):
    UserFactory(username="taras", password="test-pass-123")
    access = api.post(
        "/api/v1/auth/token/", {"username": "taras", "password": "test-pass-123"}, format="json"
    ).data["access"]

    anonymous = api.get("/api/v1/shops/mine/")
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    authenticated = api.get("/api/v1/shops/mine/")

    assert anonymous.status_code == 401
    assert authenticated.status_code == 200


def test_wrong_password_gets_no_token(api):
    UserFactory(username="taras", password="test-pass-123")

    response = api.post(
        "/api/v1/auth/token/", {"username": "taras", "password": "wrong"}, format="json"
    )

    assert response.status_code == 401
