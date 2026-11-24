from urllib.parse import urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from pymongo.errors import PyMongoError
from pymongo.uri_parser import parse_uri

from catalog import repository as catalog_repository
from core.checks import run_checks
from shopfinder import __version__, mongo
from stats import repository as stats_repository


def describe_database() -> str:
    db = settings.DATABASES["default"]
    return f"{db['USER']}@{db['HOST']}:{db['PORT']}/{db['NAME']}"


def describe_mongo() -> str:
    hosts = ",".join(f"{host}:{port}" for host, port in parse_uri(settings.MONGO_URL)["nodelist"])
    return f"{hosts}/{settings.MONGO_DB}"


def describe_redis() -> str:
    parts = urlsplit(settings.REDIS_URL)
    return f"{parts.hostname}:{parts.port or 6379}{parts.path}"


def pending_migrations() -> list[str]:
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    return [f"{migration.app_label}.{migration.name}" for migration, _ in plan]


def missing_mongo_indexes() -> list[str]:
    db = mongo.database()
    expected = {
        catalog_repository.COLLECTION: catalog_repository.INDEX_NAMES,
        stats_repository.COLLECTION: stats_repository.INDEX_NAMES,
    }
    missing = []
    for collection, names in expected.items():
        present = set(db[collection].index_information())
        missing += [f"{collection}.{name}" for name in names if name not in present]
    return missing


class Command(BaseCommand):
    help = "Print the settings that matter and check every dependency. Exits 1 on a problem."

    def handle(self, *args, **options) -> None:
        self.stdout.write(f"shop-finder-api {__version__}")
        self.stdout.write(f"  debug       {settings.DEBUG}")
        self.stdout.write(f"  hosts       {', '.join(settings.ALLOWED_HOSTS)}")
        self.stdout.write(f"  postgres    {describe_database()}")
        self.stdout.write(f"  mongo       {describe_mongo()}")
        self.stdout.write(f"  redis       {describe_redis()}")
        self.stdout.write(f"  cache       {settings.CACHES['default']['BACKEND']}")

        problems = []
        for name, result in run_checks().items():
            self.stdout.write(f"  {name:<11} {result}")
            if result != "ok":
                problems.append(f"{name} is not reachable")
        if "postgres is not reachable" not in problems:
            pending = pending_migrations()
            self.stdout.write(f"  migrations  {len(pending)} pending")
            if pending:
                problems.append(f"run migrate: {', '.join(pending)}")
        if "mongo is not reachable" not in problems:
            try:
                missing = missing_mongo_indexes()
            except PyMongoError as error:
                missing = [f"cannot list indexes ({type(error).__name__})"]
            self.stdout.write(f"  mongo index {'ok' if not missing else 'missing'}")
            if missing:
                problems.append(f"run ensure_mongo: {', '.join(missing)}")

        if problems:
            raise CommandError("; ".join(problems))
        self.stdout.write(self.style.SUCCESS("all good"))
