from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from kombu.exceptions import OperationalError
from rest_framework.throttling import ScopedRateThrottle

from imports import tasks
from imports.fetch import MAX_BYTES, Download, FetchError
from imports.models import FeedImport
from imports.services import RetryLater, run_import
from offers.models import Offer
from tests.factories import ShopFactory

pytestmark = pytest.mark.django_db

FEED_URL = "https://feeds.shop.example/prices.csv"


def feed_csv(*lines: str) -> bytes:
    return "\n".join(["barcode,price,quantity", *lines]).encode()


def served(content: bytes):
    return lambda url: Download(content, "text/csv")


def url_import(shop, url: str = FEED_URL) -> FeedImport:
    return FeedImport.objects.create(shop=shop, created_by=shop.owner, url=url)


def test_import_applies_known_barcodes_and_reports_the_rest(products, make_product):
    shop = ShopFactory()
    milk, bread = make_product(), make_product()
    Offer.objects.create(shop=shop, product_id=bread["id"], price=99, quantity=1)
    content = feed_csv(
        f"{milk['barcode']},49.90,3",
        f"{bread['barcode']},20,0",
        "2009999999997,5,1",  # valid EAN-13 that is not in the catalogue
        "1234567890123,5,1",  # not a valid EAN-13
    )

    feed = run_import(url_import(shop).pk, products=products, fetch=served(content))

    assert (feed.status, feed.rows_total, feed.rows_applied, feed.rows_failed) == ("done", 4, 2, 2)
    assert [error["line"] for error in feed.errors] == [4, 5]
    offers = {offer.product_id: offer for offer in Offer.objects.filter(shop=shop)}
    assert (offers[milk["id"]].price, offers[milk["id"]].quantity) == (Decimal("49.90"), 3)
    assert (offers[bread["id"]].price, offers[bread["id"]].quantity) == (Decimal("20.00"), 0)


def test_same_url_with_unchanged_content_is_skipped(products, make_product):
    shop = ShopFactory()
    content = feed_csv(f"{make_product()['barcode']},10,1")
    run_import(url_import(shop).pk, products=products, fetch=served(content))

    again = run_import(url_import(shop).pk, products=products, fetch=served(content))

    assert again.status == "unchanged"


def test_finished_import_is_not_run_twice(products, make_product):
    shop = ShopFactory()
    feed = url_import(shop)
    content = feed_csv(f"{make_product()['barcode']},10,1")
    run_import(feed.pk, products=products, fetch=served(content))

    def must_not_download(url):
        raise AssertionError("downloaded again")

    assert run_import(feed.pk, products=products, fetch=must_not_download).status == "done"


@pytest.mark.parametrize(
    "fetch, status",
    [
        (lambda url: (_ for _ in ()).throw(FetchError("404", transient=False)), "failed"),
        (served(b"not,a,feed\n1,2,3"), "failed"),
    ],
    ids=["download refused", "unreadable feed"],
)
def test_permanent_problems_fail_the_import(products, fetch, status):
    feed = run_import(url_import(ShopFactory()).pk, products=products, fetch=fetch)

    assert feed.status == status
    assert feed.error


def test_temporary_problem_asks_for_a_retry(products):
    def flaky(url):
        raise FetchError("the server answered 503", transient=True)

    with pytest.raises(RetryLater):
        run_import(url_import(ShopFactory()).pk, products=products, fetch=flaky)


def test_task_gives_up_after_the_last_retry(monkeypatch):
    calls = []

    def always_down(url):
        calls.append(url)
        raise FetchError("the server answered 503", transient=True)

    monkeypatch.setattr(tasks, "fetch_feed", always_down)
    # Eager mode runs each retry at once, but only if Retry is not propagated as an error.
    monkeypatch.setitem(tasks.import_feed.app.conf, "task_eager_propagates", False)
    feed = url_import(ShopFactory())

    tasks.import_feed.delay(feed.pk)

    feed.refresh_from_db()
    assert feed.status == "failed"
    assert "gave up after 5 attempts" in feed.error
    assert len(calls) == feed.attempts == tasks.MAX_RETRIES + 1


def test_retry_reason_is_shown_and_cleared_by_a_later_success(monkeypatch, make_product):
    answers = iter([FetchError("the server answered 503", transient=True)])
    content = feed_csv(f"{make_product()['barcode']},10,1")
    seen_errors = []

    def flaky_then_fine(url):
        seen_errors.append(FeedImport.objects.get(url=url).error)
        if error := next(answers, None):
            raise error
        return Download(content, "text/csv")

    monkeypatch.setattr(tasks, "fetch_feed", flaky_then_fine)
    monkeypatch.setitem(tasks.import_feed.app.conf, "task_eager_propagates", False)
    feed = url_import(ShopFactory())

    tasks.import_feed.delay(feed.pk)

    feed.refresh_from_db()
    assert seen_errors == ["", "the server answered 503; trying again"]
    assert (feed.status, feed.error, feed.attempts) == ("done", "", 2)


def test_import_deleted_while_queued_is_skipped():
    feed = url_import(ShopFactory())
    feed.shop.delete()

    assert tasks.import_feed.delay(feed.pk).get() == "missing"


def test_unexpected_error_does_not_leave_the_import_running(monkeypatch):
    def broken(url):
        raise KeyError("bug")

    monkeypatch.setattr(tasks, "fetch_feed", broken)
    feed = url_import(ShopFactory())

    with pytest.raises(KeyError):
        tasks.import_feed.delay(feed.pk)

    feed.refresh_from_db()
    assert feed.status == "failed"


def test_retry_delay_grows_and_is_capped():
    assert [tasks.retry_delay_s(n) for n in range(6)] == [30, 60, 120, 240, 480, 600]


def imports_url(shop) -> str:
    return f"/api/v1/shops/{shop.pk}/imports/"


def test_upload_is_imported_in_the_background(
    user_api, user, make_product, django_capture_on_commit_callbacks
):
    shop = ShopFactory(owner=user)
    upload = SimpleUploadedFile(
        "prices.csv", feed_csv(f"{make_product()['barcode']},10,1"), content_type="text/csv"
    )

    with django_capture_on_commit_callbacks(execute=True):
        response = user_api.post(imports_url(shop), {"file": upload}, format="multipart")

    assert response.status_code == 202
    feed = FeedImport.objects.get(pk=response.data["id"])
    assert (feed.status, feed.rows_applied, feed.content) == ("done", 1, None)
    assert Offer.objects.filter(shop=shop).count() == 1


def test_url_import_is_queued(user_api, user, monkeypatch, django_capture_on_commit_callbacks):
    queued = []
    monkeypatch.setattr(tasks.import_feed, "delay", queued.append)
    shop = ShopFactory(owner=user)

    with django_capture_on_commit_callbacks(execute=True):
        response = user_api.post(imports_url(shop), {"url": FEED_URL}, format="json")

    assert response.status_code == 202
    assert response.data["status"] == "queued"
    assert queued == [response.data["id"]]


def test_import_fails_cleanly_when_the_queue_is_down(
    user_api, user, monkeypatch, django_capture_on_commit_callbacks
):
    def broker_down(import_id):
        raise OperationalError("connection refused")

    monkeypatch.setattr(tasks.import_feed, "delay", broker_down)

    with django_capture_on_commit_callbacks(execute=True):
        response = user_api.post(
            imports_url(ShopFactory(owner=user)), {"url": FEED_URL}, format="json"
        )

    assert response.status_code == 202
    assert FeedImport.objects.get(pk=response.data["id"]).status == "failed"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"url": "http://feeds.shop.example/prices.csv"},
        {"url": "not a url"},
    ],
)
def test_invalid_import_request(user_api, user, body):
    response = user_api.post(imports_url(ShopFactory(owner=user)), body, format="json")

    assert response.status_code == 400


def test_url_and_file_together_are_rejected(user_api, user):
    upload = SimpleUploadedFile("prices.csv", b"barcode,price,quantity\n")

    response = user_api.post(
        imports_url(ShopFactory(owner=user)), {"url": FEED_URL, "file": upload}, format="multipart"
    )

    assert response.status_code == 400


def test_oversized_upload_is_refused_before_reading(user_api, user):
    upload = SimpleUploadedFile("big.csv", b"x" * (MAX_BYTES + 100 * 1024))

    response = user_api.post(imports_url(ShopFactory(owner=user)), {"file": upload})

    assert response.status_code == 413
    assert not FeedImport.objects.exists()


def test_imports_belong_to_the_shop_owner(user_api, api):
    foreign = ShopFactory()
    feed = url_import(foreign)

    assert api.get(imports_url(foreign)).status_code == 401
    assert user_api.get(imports_url(foreign)).status_code == 404
    assert user_api.post(imports_url(foreign), {"url": FEED_URL}).status_code == 404
    assert user_api.get(f"/api/v1/imports/{feed.pk}/").status_code == 404


def test_owner_sees_the_import_history(user_api, user):
    shop = ShopFactory(owner=user)
    feed = url_import(shop)

    listed = user_api.get(imports_url(shop))
    detail = user_api.get(f"/api/v1/imports/{feed.pk}/")

    assert [row["id"] for row in listed.data["results"]] == [feed.pk]
    assert detail.data["url"] == FEED_URL
    assert "content" not in detail.data


def test_starting_imports_is_throttled(user_api, user, monkeypatch):
    monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "imports", "1/hour")
    monkeypatch.setattr(tasks.import_feed, "delay", lambda import_id: None)
    shop = ShopFactory(owner=user)

    first = user_api.post(imports_url(shop), {"url": FEED_URL}, format="json")
    second = user_api.post(imports_url(shop), {"url": FEED_URL}, format="json")
    listing = user_api.get(imports_url(shop))

    assert (first.status_code, second.status_code, listing.status_code) == (202, 429, 200)
