import hashlib
import logging
from collections.abc import Callable

from django.db import transaction
from django.utils import timezone

from catalog.repository import ProductRepository
from imports.feeds import FeedFormatError, RowError, parse_feed
from imports.fetch import Download, FetchError
from imports.models import FeedImport
from offers.models import Offer

log = logging.getLogger(__name__)

MAX_STORED_ERRORS = 50
OPEN = (FeedImport.Status.QUEUED, FeedImport.Status.RUNNING)

Fetch = Callable[[str], Download]


class RetryLater(Exception):
    """A temporary failure (network, 5xx); the task decides whether to try again."""


def run_import(import_id: int, *, products: ProductRepository, fetch: Fetch) -> FeedImport:
    with transaction.atomic():
        feed = FeedImport.objects.select_for_update().select_related("shop").get(pk=import_id)
        if feed.status not in OPEN:
            return feed  # already finished: a duplicate task message is a no-op
        feed.status = FeedImport.Status.RUNNING
        feed.attempts += 1
        feed.started_at = feed.started_at or timezone.now()
        feed.save(update_fields=["status", "attempts", "started_at"])

    try:
        download = _content(feed, fetch)
    except FetchError as error:
        if error.transient:
            raise RetryLater(str(error)) from error
        return mark_failed(feed.pk, str(error))

    digest = hashlib.sha256(download.content).hexdigest()
    if feed.url and digest == _last_applied_digest(feed):
        return _finish(feed, FeedImport.Status.UNCHANGED, digest=digest)
    try:
        rows, errors = parse_feed(download.content, download.content_type)
    except FeedFormatError as error:
        return mark_failed(feed.pk, str(error))

    rows_total = len(rows) + len(errors)
    ids = products.ids_by_barcode([row.barcode for row in rows])
    known = [row for row in rows if row.barcode in ids]
    errors += [
        RowError(row.line, f"barcode {row.barcode} is not in the catalogue")
        for row in rows
        if row.barcode not in ids
    ]
    offers = [
        Offer(shop=feed.shop, product_id=ids[row.barcode], price=row.price, quantity=row.quantity)
        for row in known
    ]
    with transaction.atomic():
        # One statement per batch: INSERT ... ON CONFLICT (shop, product_id) DO UPDATE.
        Offer.objects.bulk_create(
            offers,
            update_conflicts=True,
            unique_fields=["shop", "product_id"],
            update_fields=["price", "quantity", "updated_at"],
            batch_size=1000,
        )
        feed.rows_total = rows_total
        feed.rows_applied = len(offers)
        feed.rows_failed = len(errors)
        feed.errors = [
            {"line": error.line, "message": error.message}
            for error in sorted(errors, key=lambda error: error.line)[:MAX_STORED_ERRORS]
        ]
        return _finish(feed, FeedImport.Status.DONE, digest=digest)


def mark_failed(import_id: int, reason: str) -> FeedImport:
    feed = FeedImport.objects.get(pk=import_id)
    feed.status = FeedImport.Status.FAILED
    feed.error = reason[:500]
    feed.content = None
    feed.finished_at = timezone.now()
    feed.save(update_fields=["status", "error", "content", "finished_at"])
    log.warning("import=%s shop=%s failed: %s", feed.pk, feed.shop_id, feed.error)
    return feed


def _content(feed: FeedImport, fetch: Fetch) -> Download:
    if feed.content is not None:
        return Download(bytes(feed.content), feed.content_type)
    return fetch(feed.url)


def _last_applied_digest(feed: FeedImport) -> str | None:
    """Re-reading a URL whose content has not changed since the last import is a no-op."""
    return (
        FeedImport.objects.filter(shop_id=feed.shop_id, url=feed.url, status=FeedImport.Status.DONE)
        .exclude(pk=feed.pk)
        .order_by("-finished_at")
        .values_list("content_sha256", flat=True)
        .first()
    )


def _finish(feed: FeedImport, status: str, *, digest: str) -> FeedImport:
    feed.status = status
    feed.error = ""
    feed.content_sha256 = digest
    feed.content = None
    feed.finished_at = timezone.now()
    feed.save()
    log.info(
        "import=%s shop=%s %s applied=%s failed=%s",
        feed.pk,
        feed.shop_id,
        status,
        feed.rows_applied,
        feed.rows_failed,
    )
    return feed
