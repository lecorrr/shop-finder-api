import pytest
from rest_framework.exceptions import ValidationError

from catalog.attributes import parse_attribute_filter, validate_attributes


@pytest.mark.parametrize(
    "category, attributes",
    [
        ("drinks", {"volume_l": 0.5}),
        ("drinks", {"volume_l": 0.75, "abv": 12.5}),
        ("shoes", {"size_eu": 42}),
        ("clothes", {"size": "XL", "color": "red"}),
        ("food", {}),
        ("household", {}),
    ],
)
def test_valid_attributes(category, attributes):
    assert validate_attributes(category, attributes) == attributes


@pytest.mark.parametrize(
    "category, attributes, field",
    [
        ("drinks", {}, "volume_l"),  # required
        ("drinks", {"volume_l": 0}, "volume_l"),
        ("drinks", {"volume_l": 1, "abv": 95}, "abv"),
        ("shoes", {"size_eu": 60}, "size_eu"),
        ("clothes", {"size": "XXS"}, "size"),
        ("food", {"colour": "red"}, "colour"),  # not an attribute of food
    ],
)
def test_invalid_attributes(category, attributes, field):
    with pytest.raises(ValidationError) as error:
        validate_attributes(category, attributes)
    assert field in error.value.detail


def test_filter_values_are_typed_like_the_stored_ones():
    assert parse_attribute_filter("shoes", "size_eu", "42") == 42.0
    assert parse_attribute_filter("clothes", "size", "M") == "M"


@pytest.mark.parametrize("name, raw", [("size_eu", "big"), ("colour", "red")])
def test_invalid_filter(name, raw):
    with pytest.raises(ValidationError):
        parse_attribute_filter("shoes", name, raw)
