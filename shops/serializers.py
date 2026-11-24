from rest_framework import serializers

from shops.models import Shop

MAX_RADIUS_KM = 50


class NearQuerySerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    radius_km = serializers.FloatField(min_value=0.1, max_value=MAX_RADIUS_KM, default=2)


class ShopSerializer(serializers.ModelSerializer):
    owner = serializers.CharField(source="owner.username", read_only=True)
    distance_km = serializers.SerializerMethodField()

    class Meta:
        model = Shop
        fields = [
            "id",
            "name",
            "address",
            "latitude",
            "longitude",
            "opening_hours",
            "is_active",
            "owner",
            "distance_km",
        ]

    def get_distance_km(self, shop: Shop) -> float | None:
        distance = getattr(shop, "distance_km", None)
        return None if distance is None else round(distance, 2)
