from django.contrib import admin

from offers.models import Offer


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ["id", "shop", "product_id", "price", "quantity", "updated_at"]
    search_fields = ["shop__name", "product_id"]
    autocomplete_fields = ["shop"]
