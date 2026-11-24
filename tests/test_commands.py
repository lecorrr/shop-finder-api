import pytest
from django.core.management import CommandError, call_command

from catalog.repository import INDEX_NAMES
from core import checks
from offers.models import Offer
from shops.models import Shop

pytestmark = pytest.mark.django_db


def test_ensure_mongo_can_run_again(mongo_db):
    call_command("ensure_mongo")
    call_command("ensure_mongo")

    assert set(INDEX_NAMES) <= set(mongo_db["products"].index_information())


def test_seed_demo_loads_once_and_reloads_on_reset(products, capsys):
    call_command("seed_demo", password="demo-pass-123")
    first = (Shop.objects.count(), Offer.objects.count(), products.products.count_documents({}))
    call_command("seed_demo")
    second = (Shop.objects.count(), Offer.objects.count(), products.products.count_documents({}))
    call_command("seed_demo", reset=True, password="demo-pass-123")
    third = (Shop.objects.count(), Offer.objects.count(), products.products.count_documents({}))

    assert first == second == third
    assert first[0] == 7
    assert "already loaded" in capsys.readouterr().out


def test_doctor_passes_when_everything_is_ready(capsys):
    call_command("doctor")

    assert "all good" in capsys.readouterr().out


def test_doctor_fails_and_says_what_to_do(mongo_db):
    mongo_db["products"].drop_index("product_category")
    try:
        with pytest.raises(CommandError, match="ensure_mongo"):
            call_command("doctor")
    finally:
        call_command("ensure_mongo")


def test_doctor_reports_an_unreachable_dependency(monkeypatch):
    def redis_down():
        raise ConnectionError("refused")

    monkeypatch.setitem(checks.CHECKS, "redis", redis_down)

    with pytest.raises(CommandError, match="redis is not reachable"):
        call_command("doctor")
