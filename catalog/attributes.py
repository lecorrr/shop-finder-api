"""What each category's products may say about themselves.

The catalogue lives in MongoDB because these differ by category: a drink has a volume, a
shoe has a size. Each category's attributes are still validated, here and by a schema
validator on the collection.
"""

from rest_framework import serializers

CLOTHING_SIZES = ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]


class DrinksAttributes(serializers.Serializer):
    volume_l = serializers.FloatField(min_value=0.05, max_value=20)
    abv = serializers.FloatField(min_value=0, max_value=80, required=False)


class FoodAttributes(serializers.Serializer):
    weight_g = serializers.IntegerField(min_value=1, max_value=100_000, required=False)


class ShoesAttributes(serializers.Serializer):
    size_eu = serializers.FloatField(min_value=16, max_value=52)
    color = serializers.CharField(max_length=30, required=False)


class ClothesAttributes(serializers.Serializer):
    size = serializers.ChoiceField(choices=CLOTHING_SIZES)
    color = serializers.CharField(max_length=30, required=False)


class HouseholdAttributes(serializers.Serializer):
    pass


class ElectronicsAttributes(serializers.Serializer):
    model = serializers.CharField(max_length=60, required=False)


ATTRIBUTES_BY_CATEGORY: dict[str, type[serializers.Serializer]] = {
    "drinks": DrinksAttributes,
    "food": FoodAttributes,
    "shoes": ShoesAttributes,
    "clothes": ClothesAttributes,
    "household": HouseholdAttributes,
    "electronics": ElectronicsAttributes,
}
CATEGORIES = list(ATTRIBUTES_BY_CATEGORY)


def validate_attributes(category: str, attributes: dict) -> dict:
    """Return the attributes cleaned for this category; unknown keys are an error."""
    serializer_class = ATTRIBUTES_BY_CATEGORY[category]
    serializer = serializer_class(data=attributes)
    serializer.is_valid(raise_exception=True)
    unknown = sorted(set(attributes) - set(serializer.fields))
    if unknown:
        raise serializers.ValidationError(
            {name: [f"not an attribute of {category}"] for name in unknown}
        )
    return dict(serializer.validated_data)


def parse_attribute_filter(category: str, name: str, raw: str):
    """Turn ?attr.size_eu=42 into the typed value stored in MongoDB."""
    fields = ATTRIBUTES_BY_CATEGORY[category]().fields
    if name not in fields:
        raise serializers.ValidationError({f"attr.{name}": [f"not an attribute of {category}"]})
    try:
        return fields[name].run_validation(raw)
    except serializers.ValidationError as error:
        raise serializers.ValidationError({f"attr.{name}": error.detail}) from error
