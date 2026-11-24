from decimal import Decimal

from rest_framework import serializers

from catalog.attributes import CATEGORIES
from shops.serializers import MAX_RADIUS_KM


class OfferWriteSerializer(serializers.Serializer):
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    quantity = serializers.IntegerField(min_value=0, max_value=1_000_000)


class OfferProductSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    brand = serializers.CharField()
    category = serializers.CharField()
    barcode = serializers.CharField(allow_null=True)
    attributes = serializers.DictField()
    status = serializers.CharField()


class OfferSerializer(serializers.Serializer):
    product = OfferProductSerializer(allow_null=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    quantity = serializers.IntegerField()
    updated_at = serializers.DateTimeField()


class SearchShopSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    address = serializers.CharField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    distance_km = serializers.FloatField()


class SearchResultSerializer(OfferSerializer):
    shop = SearchShopSerializer()


class SearchQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=100)
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    radius_km = serializers.FloatField(min_value=0.1, max_value=MAX_RADIUS_KM, default=2)
    category = serializers.ChoiceField(choices=CATEGORIES, required=False)
    max_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.01"), required=False
    )
