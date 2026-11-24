from decimal import Decimal

from catalog.repository import ACTIVE, ProductRepository
from offers.models import Offer
from shops.models import Shop


class UnknownProduct(Exception):
    pass


def set_offer(
    *, shop: Shop, product_id: str, price: Decimal, quantity: int, products: ProductRepository
) -> tuple[Offer, bool]:
    """Create or replace the shop's offer; returns (offer, created)."""
    product = products.get(product_id)
    if product is None or product["status"] != ACTIVE:
        raise UnknownProduct(product_id)
    return Offer.objects.update_or_create(
        shop=shop, product_id=product_id, defaults={"price": price, "quantity": quantity}
    )
