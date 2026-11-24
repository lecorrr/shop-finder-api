from urllib.parse import urlsplit

from rest_framework import serializers

from imports.fetch import MAX_BYTES
from imports.models import FeedImport


class FeedImportSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeedImport
        fields = [
            "id",
            "shop",
            "url",
            "file_name",
            "status",
            "attempts",
            "rows_total",
            "rows_applied",
            "rows_failed",
            "errors",
            "error",
            "created_at",
            "started_at",
            "finished_at",
        ]
        read_only_fields = fields


class FeedImportCreateSerializer(serializers.Serializer):
    """Either a URL the worker downloads, or a file uploaded with the request."""

    url = serializers.URLField(max_length=500, required=False)
    file = serializers.FileField(required=False, max_length=200)

    def validate_url(self, url: str) -> str:
        if urlsplit(url).scheme != "https":
            raise serializers.ValidationError("only https:// feed URLs are accepted")
        return url

    def validate_file(self, file):
        if file.size > MAX_BYTES:
            raise serializers.ValidationError("the feed is larger than 5 MB")
        if file.size == 0:
            raise serializers.ValidationError("the file is empty")
        return file

    def validate(self, attrs: dict) -> dict:
        if ("url" in attrs) == ("file" in attrs):
            raise serializers.ValidationError("send either url or file, not both")
        return attrs
