"""One MongoDB client per process, created on first use.

PyMongo clients are not fork-safe, so nothing connects at import time: gunicorn and
Celery workers each open their own client after they fork.
"""

from functools import cache

from django.conf import settings
from pymongo import MongoClient
from pymongo.database import Database


@cache
def client() -> MongoClient:
    return MongoClient(
        settings.MONGO_URL,
        serverSelectionTimeoutMS=settings.MONGO_TIMEOUT_MS,
        connectTimeoutMS=settings.MONGO_TIMEOUT_MS,
        tz_aware=True,
        appname="shop-finder-api",
    )


def database() -> Database:
    return client()[settings.MONGO_DB]
