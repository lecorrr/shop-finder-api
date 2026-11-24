"""Can the API reach what it depends on? Used by /api/v1/health/ and `manage.py doctor`."""

import logging
from collections.abc import Callable

import redis
from django.conf import settings
from django.db import connection

from shopfinder import mongo

log = logging.getLogger(__name__)

REDIS_TIMEOUT_S = 2


def check_postgres() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")


def check_mongo() -> None:
    mongo.client().admin.command("ping")


def check_redis() -> None:
    with redis.Redis.from_url(
        settings.REDIS_URL,
        socket_connect_timeout=REDIS_TIMEOUT_S,
        socket_timeout=REDIS_TIMEOUT_S,
    ) as client:
        client.ping()


CHECKS: dict[str, Callable[[], None]] = {
    "postgres": check_postgres,
    "mongo": check_mongo,
    "redis": check_redis,
}


def run_checks() -> dict[str, str]:
    results = {}
    for name, check in CHECKS.items():
        try:
            check()
        except Exception as error:  # report every dependency, not just the first broken one
            log.warning("health check %s failed: %s: %s", name, type(error).__name__, error)
            results[name] = "error"
        else:
            results[name] = "ok"
    return results
