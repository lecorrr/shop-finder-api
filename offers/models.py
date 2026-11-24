from decimal import Decimal

from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q

from shops.models import Shop

object_id_validator = RegexValidator(r"^[0-9a-f]{24}$", "not a product id")


class Offer(models.Model):
    """One shop's price and stock for one catalogue product.

    product_id points into MongoDB, so there is no foreign key: the product is checked
    when the offer is written, and products are archived rather than deleted.
    """

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="offers")
    product_id = models.CharField(max_length=24, validators=[object_id_validator])
    price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    quantity = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["shop", "product_id"], name="offer_unique_per_shop"),
            models.CheckConstraint(condition=Q(price__gt=0), name="offer_price_positive"),
        ]
        indexes = [models.Index(fields=["product_id"], name="offer_product_idx")]

    def __str__(self) -> str:
        return f"{self.shop} / {self.product_id}"
