import json
from decimal import Decimal

import pytest

from catalog.barcodes import with_check_digit
from imports.feeds import MAX_ROWS, FeedFormatError, parse_feed

MILK = with_check_digit("200000000001")
BREAD = with_check_digit("200000000002")


def csv_feed(*lines: str, delimiter: str = ",") -> bytes:
    header = delimiter.join(["barcode", "price", "quantity"])
    return "\n".join([header, *lines]).encode()


def test_comma_separated_feed():
    rows, errors = parse_feed(csv_feed(f"{MILK},49.90,3", f"{BREAD},20,0"), "text/csv")

    assert [(row.barcode, row.price, row.quantity) for row in rows] == [
        (MILK, Decimal("49.90"), 3),
        (BREAD, Decimal("20.00"), 0),
    ]
    assert errors == []


@pytest.mark.parametrize("price", ["1 249,50", "1\u00a0249,50", "1249.50"])
def test_spreadsheet_export_with_semicolons_decimal_commas_and_bom(price):
    content = "\ufeffBarcode;Price;Quantity\n" + f"{MILK};{price};2\n"

    rows, _ = parse_feed(content.encode(), "text/csv")

    assert rows[0].price == Decimal("1249.50")


@pytest.mark.parametrize(
    "wrap", [lambda items: items, lambda items: {"items": items}], ids=["list", "object"]
)
def test_json_feed(wrap):
    content = json.dumps(wrap([{"barcode": MILK, "price": 49.9, "quantity": 3}])).encode()

    rows, errors = parse_feed(content, "application/json")

    assert [(row.barcode, row.price) for row in rows] == [(MILK, Decimal("49.90"))]
    assert errors == []


@pytest.mark.parametrize(
    "line, message",
    [
        ("1234567890123,10,1", "not a valid EAN-13"),
        (f"{MILK},abc,1", "not a number"),
        (f"{MILK},0,1", "out of range"),
        (f"{MILK},-3,1", "out of range"),
        (f"{MILK},NaN,1", "out of range"),
        (f"{MILK},1.999,1", "two decimal places"),
        (f"{MILK},10,-1", "not a whole number"),
        (f"{MILK},10,2.5", "not a whole number"),
        (f"{MILK},10,", "not a whole number"),
    ],
)
def test_bad_row_is_reported_and_skipped(line, message):
    rows, errors = parse_feed(csv_feed(f"{BREAD},20,1", line), "text/csv")

    assert [row.barcode for row in rows] == [BREAD]
    assert len(errors) == 1
    assert errors[0].line == 3
    assert message in errors[0].message


def test_repeated_barcode_keeps_the_first_row():
    rows, errors = parse_feed(csv_feed(f"{MILK},10,1", f"{MILK},12,1"), "text/csv")

    assert [row.price for row in rows] == [Decimal("10.00")]
    assert "repeats" in errors[0].message


@pytest.mark.parametrize(
    "content, content_type",
    [
        (b"barcode,price\n1,2\n", "text/csv"),  # no quantity column
        (b"", "text/csv"),
        (b"\xff\xfe\x00b", "text/csv"),  # not UTF-8
        (b"[1, 2", "application/json"),
        (b'{"rows": []}', "application/json"),
    ],
)
def test_unreadable_feed_fails_as_a_whole(content, content_type):
    with pytest.raises(FeedFormatError):
        parse_feed(content, content_type)


def test_json_rows_must_be_objects():
    _, errors = parse_feed(b"[1, 2]", "application/json")

    assert len(errors) == 2


def test_too_many_rows():
    lines = [f"{MILK},1,1"] * (MAX_ROWS + 1)

    with pytest.raises(FeedFormatError, match="more than"):
        parse_feed(csv_feed(*lines), "text/csv")


def test_json_is_detected_without_a_content_type():
    content = json.dumps([{"barcode": MILK, "price": "5", "quantity": 1}]).encode()

    rows, _ = parse_feed(content, "application/octet-stream")

    assert len(rows) == 1
