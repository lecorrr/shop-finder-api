from django.contrib import admin

from shops.models import Shop


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ["name", "owner", "address", "is_active", "updated_at"]
    list_filter = ["is_active"]
    search_fields = ["name", "address", "owner__username"]
    autocomplete_fields = ["owner"]
