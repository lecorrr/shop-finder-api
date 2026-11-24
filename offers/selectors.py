from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import QuerySet

from catalog.repository import ProductRepository
from offers.models import Offer
from shops.geo import bounding_box, distance_expression

# Products considered per search, best text match first; the rest are not looked up.
MAX_PRODUCTS = 200


@dataclass(frozen=True)
class SearchQuery:
    q: str
    lat: float
    lon: float
    radius_km: float
    category: str | None = None
    attributes: dict = field(default_factory=dict)
    max_price: Decimal | None = None


def search_offers(
    query: SearchQuery, products: ProductRepository
) -> tuple[QuerySet[Offer], dict[str, dict]]:
    """Offers in stock within the radius, nearest then cheapest, plus their product documents.

    Two stores, two steps: MongoDB finds the products that match the words, then one
    Postgres query finds the shops nearby that have them.
    """
    documents, _ = products.search(
        text=query.q, category=query.category, attributes=query.attributes, limit=MAX_PRODUCTS
    )
    by_id = {str(document["_id"]): document for document in documents}
    if not by_id:
        return Offer.objects.none(), {}
    box = bounding_box(query.lat, query.lon, query.radius_km)
    offers = (
        Offer.objects.filter(
            product_id__in=list(by_id),
            quantity__gt=0,
            shop__is_active=True,
            shop__latitude__range=(box.min_lat, box.max_lat),
            shop__longitude__range=(box.min_lon, box.max_lon),
        )
        .annotate(
            distance_km=distance_expression(
                query.lat, query.lon, "shop__latitude", "shop__longitude"
            )
        )
        .filter(distance_km__lte=query.radius_km)
        .select_related("shop")
        .order_by("distance_km", "price", "id")
    )
    if query.max_price is not None:
        offers = offers.filter(price__lte=query.max_price)
    return offers, by_id
