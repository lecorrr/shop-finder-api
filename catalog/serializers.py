from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from catalog.attributes import CATEGORIES, validate_attributes
from catalog.barcodes import is_valid_ean13

MAX_TAGS = 20


class ProductSerializer(serializers.Serializer):
    """What the API returns for a product (documents come from MongoDB as dicts)."""

    id = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    brand = serializers.CharField(read_only=True)
    category = serializers.CharField(read_only=True)
    barcode = serializers.CharField(read_only=True, allow_null=True)
    attributes = serializers.DictField(read_only=True)
    tags = serializers.ListField(child=serializers.CharField(), read_only=True)
    status = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class ProductWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    brand = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    category = serializers.ChoiceField(choices=CATEGORIES)
    barcode = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    attributes = serializers.DictField(required=False, default=dict)
    tags = serializers.ListField(
        child=serializers.CharField(max_length=40), required=False, default=list
    )

    def validate_barcode(self, value: str | None) -> str | None:
        if value and not is_valid_ean13(value):
            raise serializers.ValidationError("not a valid EAN-13 barcode")
        return value or None

    def validate_tags(self, tags: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(tag.strip().lower() for tag in tags if tag.strip()))
        if len(cleaned) > MAX_TAGS:
            raise serializers.ValidationError(f"at most {MAX_TAGS} tags")
        return cleaned

    def validate(self, attrs: dict) -> dict:
        try:
            attrs["attributes"] = validate_attributes(attrs["category"], attrs["attributes"])
        except serializers.ValidationError as error:
            raise serializers.ValidationError({"attributes": error.detail}) from error
        return attrs


class ProductQuerySerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True, max_length=100)
    category = serializers.ChoiceField(choices=CATEGORIES, required=False)


@extend_schema_serializer(many=False)  # one page object, not a list of them
class ProductPageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = ProductSerializer(many=True)
