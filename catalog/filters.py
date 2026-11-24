from rest_framework import serializers
from rest_framework.request import Request

from catalog.attributes import parse_attribute_filter

ATTRIBUTE_PREFIX = "attr."


def attribute_filters(request: Request, category: str | None) -> dict:
    """?attr.size_eu=42 style filters, typed by the category's attribute rules."""
    raw = {
        key.removeprefix(ATTRIBUTE_PREFIX): value
        for key, value in request.query_params.items()
        if key.startswith(ATTRIBUTE_PREFIX)
    }
    if raw and not category:
        raise serializers.ValidationError({"category": ["required with attr.* filters"]})
    return {name: parse_attribute_filter(category, name, value) for name, value in raw.items()}
