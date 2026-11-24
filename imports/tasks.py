import logging

from celery import shared_task
from kombu.exceptions import OperationalError
from pymongo.errors import PyMongoError

from catalog.repository import product_repository
from imports.fetch import fetch_feed
from imports.models import FeedImport
from imports.services import RetryLater, mark_failed, run_import

log = logging.getLogger(__name__)

MAX_RETRIES = 4


def retry_delay_s(retries: int) -> int:
    return min(30 * 2**retries, 600)


@shared_task(bind=True, max_retries=MAX_RETRIES)
def import_feed(self, import_id: int) -> str:
    try:
        feed = run_import(import_id, products=product_repository(), fetch=fetch_feed)
    except FeedImport.DoesNotExist:
        # The shop, and its imports with it, was deleted while this task waited in the queue.
        log.warning("import=%s no longer exists, skipped", import_id)
        return "missing"
    except (RetryLater, PyMongoError) as error:
        if self.request.retries >= self.max_retries:
            attempts = self.request.retries + 1
            return mark_failed(import_id, f"{error} (gave up after {attempts} attempts)").status
        # Show the owner why the import is taking long; a later success clears it.
        FeedImport.objects.filter(pk=import_id).update(error=f"{error}; trying again")
        raise self.retry(exc=error, countdown=retry_delay_s(self.request.retries)) from error
    except Exception:
        # Leave no import "running" forever; the traceback goes to the worker log.
        mark_failed(import_id, "internal error")
        raise
    return feed.status


def queue_import(import_id: int) -> None:
    """Called after the import row is committed, so the worker can always see it."""
    try:
        import_feed.delay(import_id)
    except OperationalError as error:
        log.error("import=%s not queued: %s", import_id, error)
        mark_failed(import_id, "the import queue is unavailable, try again later")
