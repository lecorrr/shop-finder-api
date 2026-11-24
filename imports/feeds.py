"""Reading a shop's feed: CSV or JSON rows of barcode, price and quantity.

Pure functions: bytes in, rows and row errors out. One bad row is reported and skipped;
only a feed that cannot be read at all fails as a whole.
"""

import csv
import io
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from catalog.barcodes import is_valid_ean13

MAX_ROWS = 10_000
MAX_PRICE = Decimal("100000000")
REQUIRED_COLUMNS = ("barcode", "price", "quantity")


@dataclass(frozen=True)
class FeedRow:
    line: int
    barcode: str
    price: Decimal
    quantity: int


@dataclass(frozen=True)
class RowError:
    line: int
    message: str


class FeedFormatError(ValueError):
    pass


def parse_feed(content: bytes, content_type: str) -> tuple[list[FeedRow], list[RowError]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise FeedFormatError("the feed is not UTF-8 text") from error
    records = _json_records(text) if _is_json(content_type, text) else _csv_records(text)
    if len(records) > MAX_ROWS:
        raise FeedFormatError(f"more than {MAX_ROWS} rows")
    rows: list[FeedRow] = []
    errors: list[RowError] = []
    seen: set[str] = set()
    for line, record in records:
        try:
            row = _row(line, record)
        except ValueError as error:
            errors.append(RowError(line, str(error)))
            continue
        if row.barcode in seen:
            errors.append(RowError(line, f"barcode {row.barcode} repeats; the first row is kept"))
            continue
        seen.add(row.barcode)
        rows.append(row)
    return rows, errors


def _is_json(content_type: str, text: str) -> bool:
    if "json" in content_type:
        return True
    return text.lstrip()[:1] in ("[", "{")


def _json_records(text: str) -> list[tuple[int, dict]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise FeedFormatError(f"invalid JSON: {error.msg} at line {error.lineno}") from error
    if isinstance(data, dict):
        data = data.get("items")
    if not isinstance(data, list):
        raise FeedFormatError('JSON must be a list of rows, or {"items": [...]}')
    return [(number, item) for number, item in enumerate(data, 1)]


def _csv_records(text: str) -> list[tuple[int, dict]]:
    first_line = text.split("\n", 1)[0]
    # Ukrainian spreadsheet exports use ";" because "," is the decimal separator.
    delimiter = max((";", ",", "\t"), key=first_line.count)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if reader.fieldnames is None:
        raise FeedFormatError("the feed is empty")
    reader.fieldnames = [name.strip().lower() for name in reader.fieldnames]
    missing = [column for column in REQUIRED_COLUMNS if column not in reader.fieldnames]
    if missing:
        raise FeedFormatError(f"missing columns: {', '.join(missing)}")
    return [(reader.line_num, record) for record in reader]


def _row(line: int, record: object) -> FeedRow:
    if not isinstance(record, dict):
        raise ValueError("not a row with barcode, price and quantity")
    barcode = str(record.get("barcode") or "").strip()
    if not is_valid_ean13(barcode):
        raise ValueError(f"barcode {barcode!r} is not a valid EAN-13")
    return FeedRow(line, barcode, _price(record.get("price")), _quantity(record.get("quantity")))


def _price(raw: object) -> Decimal:
    # "1 249,50": spreadsheets group thousands with (no-break) spaces and use a decimal comma.
    text = "".join(str(raw if raw is not None else "").split()).replace(",", ".")
    try:
        price = Decimal(text)
    except InvalidOperation as error:
        raise ValueError(f"price {raw!r} is not a number") from error
    if not price.is_finite() or price <= 0 or price >= MAX_PRICE:
        raise ValueError(f"price {raw!r} is out of range")
    if price != price.quantize(Decimal("0.01")):
        raise ValueError(f"price {raw!r} has more than two decimal places")
    return price.quantize(Decimal("0.01"))


def _quantity(raw: object) -> int:
    text = str(raw if raw is not None else "").strip()
    if not text.isdigit() or not text.isascii():
        raise ValueError(f"quantity {raw!r} is not a whole number")
    return int(text)
