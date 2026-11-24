from django.conf import settings
from django.core.management.base import BaseCommand

from catalog import repository as catalog_repository
from shopfinder import mongo
from stats import repository as stats_repository


class Command(BaseCommand):
    help = "Create or update the MongoDB validators and indexes. Safe to run on every deploy."

    def handle(self, *args, **options) -> None:
        db = mongo.database()
        catalog_repository.ensure_schema(db)
        stats_repository.ensure_schema(db, settings.SEARCH_EVENTS_KEEP_DAYS)
        self.stdout.write(self.style.SUCCESS(f"MongoDB schema is up to date in {db.name}"))
