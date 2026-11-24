"""EAN-13, the barcode on almost every product in a Ukrainian shop."""


def _check_digit(first12: str) -> int:
    total = sum(int(digit) * (3 if position % 2 else 1) for position, digit in enumerate(first12))
    return (10 - total % 10) % 10


def is_valid_ean13(code: str) -> bool:
    if len(code) != 13 or not (code.isascii() and code.isdigit()):
        return False
    return _check_digit(code[:12]) == int(code[12])


def with_check_digit(first12: str) -> str:
    """Complete twelve digits into a valid EAN-13 (for demo data and tests)."""
    if len(first12) != 12 or not (first12.isascii() and first12.isdigit()):
        raise ValueError("an EAN-13 starts with exactly 12 digits")
    return first12 + str(_check_digit(first12))
