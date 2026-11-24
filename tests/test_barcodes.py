import pytest

from catalog.barcodes import is_valid_ean13, with_check_digit


@pytest.mark.parametrize("code", ["4006381333931", "2000000000008", "5901234123457"])
def test_valid_ean13(code):
    assert is_valid_ean13(code)


@pytest.mark.parametrize(
    "code",
    [
        "4006381333932",  # wrong check digit
        "400638133393",  # 12 digits
        "40063813339310",  # 14 digits
        "40063813339a1",
        "",
        "٤٠٠٦٣٨١٣٣٣٩٣١",  # Arabic-Indic digits pass isdigit() but are not a barcode
    ],
)
def test_invalid_ean13(code):
    assert not is_valid_ean13(code)


def test_with_check_digit_completes_a_valid_code():
    assert with_check_digit("400638133393") == "4006381333931"


@pytest.mark.parametrize("first12", ["40063813339", "4006381333931", "40063813339x"])
def test_with_check_digit_needs_exactly_twelve_digits(first12):
    with pytest.raises(ValueError):
        with_check_digit(first12)
