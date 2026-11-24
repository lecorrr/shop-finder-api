"""Synthetic demo data around central Kyiv: shops, products, offers and some searches.

The barcodes start with 200, a GS1 prefix reserved for in-store use, so they can never
clash with a real product. Run migrate and ensure_mongo first.
"""

import random
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.barcodes import with_check_digit
from catalog.repository import ProductRepository
from offers.models import Offer
from shopfinder import mongo
from shops.models import Shop
from stats.repository import SearchEventRepository

DEMO_USERNAME = "demo-owner"
DEMO_EMAIL = "demo-owner@example.com"
CENTRE = (50.4501, 30.5234)

# name, latitude, longitude, categories it sells
SHOPS = [
    ("Corner Market", 50.4510, 30.5220, ["food", "drinks", "household"]),
    ("Fresh Basket", 50.4475, 30.5260, ["food", "drinks"]),
    ("Run and Walk", 50.4530, 30.5180, ["shoes", "clothes"]),
    ("Home Goods", 50.4420, 30.5300, ["household", "electronics"]),
    ("Volt Electronics", 50.4560, 30.5350, ["electronics"]),
    ("Night Shop 24", 50.4600, 30.5100, ["food", "drinks", "household"]),
    ("Left Bank Grocery", 50.4400, 30.6000, ["food", "drinks"]),
]

# base price in UAH, name, brand, category, attributes, tags
PRODUCTS = [
    ("89.90", "Oat milk", "Green Field", "drinks", {"volume_l": 1.0}, ["milk", "oat"]),
    ("42.50", "Milk 2.5%", "Morning Dew", "drinks", {"volume_l": 0.9}, ["milk", "dairy"]),
    ("24.00", "Still water", "Hill Spring", "drinks", {"volume_l": 1.5}, ["water"]),
    ("18.50", "Sparkling water", "Hill Spring", "drinks", {"volume_l": 0.5}, ["water"]),
    ("64.00", "Apple juice", "Orchard Lane", "drinks", {"volume_l": 1.0}, ["juice"]),
    ("289.00", "Dry red wine", "Old Cellar", "drinks", {"volume_l": 0.75, "abv": 12.5}, ["wine"]),
    ("38.00", "Rye bread", "Baker's Corner", "food", {"weight_g": 500}, ["bread"]),
    ("72.00", "Buckwheat", "Field Grain", "food", {"weight_g": 1000}, ["grain"]),
    ("69.90", "Dark chocolate 70%", "Cocoa Hill", "food", {"weight_g": 100}, ["chocolate"]),
    ("145.00", "Cheddar cheese", "Morning Dew", "food", {"weight_g": 200}, ["cheese"]),
    ("64.90", "Bananas", "", "food", {"weight_g": 1000}, ["fruit"]),
    ("2899.00", "Running shoes", "Stepwell", "shoes", {"size_eu": 42, "color": "black"}, []),
    ("2899.00", "Running shoes", "Stepwell", "shoes", {"size_eu": 43, "color": "black"}, []),
    ("2899.00", "Running shoes", "Stepwell", "shoes", {"size_eu": 39, "color": "white"}, []),
    ("3499.00", "Winter boots", "North Trail", "shoes", {"size_eu": 42, "color": "brown"}, []),
    ("1899.00", "Rain jacket", "North Trail", "clothes", {"size": "M", "color": "yellow"}, []),
    ("1899.00", "Rain jacket", "North Trail", "clothes", {"size": "L", "color": "yellow"}, []),
    ("249.00", "Wool socks", "Homely", "clothes", {"size": "M"}, ["socks"]),
    ("79.00", "Dish soap", "Homely", "household", {}, ["cleaning"]),
    ("59.00", "LED bulb", "Brightline", "household", {}, ["light"]),
    ("129.00", "AA batteries, 4 pcs", "Brightline", "household", {}, ["batteries"]),
    ("249.00", "USB-C cable 1 m", "Brightline", "electronics", {"model": "BL-C1"}, ["cable"]),
    ("599.00", "Phone charger 20 W", "Brightline", "electronics", {"model": "BL-20W"}, []),
    ("1999.00", "Wireless earbuds", "Volt", "electronics", {"model": "V-Buds 2"}, ["audio"]),
]

# query, how many times, how many results each search found
SEARCHES = [
    ("oat milk", 12, 3),
    ("running shoes", 8, 2),
    ("gluten free bread", 6, 0),
    ("phone charger", 5, 2),
    ("kombucha", 4, 0),
    ("rain jacket", 3, 1),
]


def demo_barcode(index: int) -> str:
    return with_check_digit(f"200{index:09d}")


class Command(BaseCommand):
    help = "Load synthetic demo shops, products, offers and searches around central Kyiv."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--reset", action="store_true", help="delete the demo data first")
        parser.add_argument("--password", help="password for the demo shop owner")

    def handle(self, *args, reset: bool, password: str | None, **options) -> None:
        db = mongo.database()
        products = ProductRepository(db)
        events = SearchEventRepository(db)
        if reset:
            self.delete_demo_data(products, events)
        elif get_user_model().objects.filter(username=DEMO_USERNAME).exists():
            self.stdout.write("demo data is already loaded; use --reset to load it again")
            return

        password = password or secrets.token_urlsafe(9)
        rng = random.Random(42)
        product_ids = self.create_products(products)
        with transaction.atomic():
            owner = get_user_model().objects.create_user(
                username=DEMO_USERNAME, email=DEMO_EMAIL, password=password
            )
            offers = self.create_shops_and_offers(owner, product_ids, rng)
        searches = self.create_searches(events, rng)
        self.stdout.write(
            self.style.SUCCESS(
                f"{len(SHOPS)} shops, {len(product_ids)} products, {offers} offers, "
                f"{searches} searches"
            )
        )
        self.stdout.write(f"shop owner: {DEMO_USERNAME} / {password}")

    def delete_demo_data(self, products: ProductRepository, events: SearchEventRepository) -> None:
        User = get_user_model()
        with transaction.atomic():
            Shop.objects.filter(owner__username=DEMO_USERNAME).delete()
            User.objects.filter(username=DEMO_USERNAME).delete()
        barcodes = [demo_barcode(index) for index in range(len(PRODUCTS))]
        products.products.delete_many({"barcode": {"$in": barcodes}})
        events.events.delete_many({"q": {"$in": [query for query, _, _ in SEARCHES]}})

    def create_products(self, products: ProductRepository) -> dict[str, tuple[str, Decimal, str]]:
        """barcode -> (product id, base price, category)"""
        created = {}
        for index, (price, name, brand, category, attributes, tags) in enumerate(PRODUCTS):
            barcode = demo_barcode(index)
            document = products.create(
                {
                    "name": name,
                    "brand": brand,
                    "category": category,
                    "barcode": barcode,
                    "attributes": attributes,
                    "tags": tags,
                }
            )
            created[barcode] = (str(document["_id"]), Decimal(price), category)
        return created

    def create_shops_and_offers(self, owner, product_ids: dict, rng: random.Random) -> int:
        offers = []
        for number, (name, lat, lon, categories) in enumerate(SHOPS, 1):
            shop = Shop.objects.create(
                owner=owner,
                name=name,
                address=f"Demo street {number}, Kyiv",
                latitude=lat,
                longitude=lon,
                opening_hours="08:00-22:00",
            )
            for product_id, base_price, category in product_ids.values():
                if category not in categories or rng.random() > 0.8:
                    continue
                price = (base_price * Decimal(rng.uniform(0.9, 1.2))).quantize(Decimal("0.01"))
                quantity = rng.choice([0, 2, 5, 12, 30])
                offers.append(
                    Offer(shop=shop, product_id=product_id, price=price, quantity=quantity)
                )
        Offer.objects.bulk_create(offers)
        return len(offers)

    def create_searches(self, events: SearchEventRepository, rng: random.Random) -> int:
        now = datetime.now(UTC)
        count = 0
        for query, times, results in SEARCHES:
            for _ in range(times):
                events.log(
                    q=query,
                    category=None,
                    lat=CENTRE[0] + rng.uniform(-0.01, 0.01),
                    lon=CENTRE[1] + rng.uniform(-0.01, 0.01),
                    radius_km=2,
                    results=results,
                    now=now - timedelta(hours=rng.uniform(1, 6 * 24)),
                )
                count += 1
        return count
