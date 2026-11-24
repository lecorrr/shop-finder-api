from rest_framework import serializers

from shops.serializers import MAX_RADIUS_KM


class MostWantedQuerySerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    radius_km = serializers.FloatField(min_value=0.1, max_value=MAX_RADIUS_KM, default=5)
    days = serializers.IntegerField(min_value=1, max_value=180, default=7)
    limit = serializers.IntegerField(min_value=1, max_value=50, default=10)
    unmet = serializers.BooleanField(default=False)


class MostWantedSerializer(serializers.Serializer):
    query = serializers.CharField()
    searches = serializers.IntegerField()
    unmet = serializers.IntegerField(help_text="Searches that found no offer at all")
    last_searched = serializers.DateTimeField()
