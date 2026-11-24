import os

# Tests need real PostgreSQL and MongoDB (see README); only the secret gets a default here.
os.environ.setdefault("DJANGO_SECRET_KEY", "tests-only-not-a-secret")

from shopfinder.settings import *  # noqa: F403

SECRET_KEY = "tests-only-not-a-secret-but-long-enough-for-hs256-signing"
MONGO_DB = "shopfinder_test"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
# Static files are not collected for tests.
MIDDLEWARE = [name for name in MIDDLEWARE if not name.startswith("whitenoise")]  # noqa: F405
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
