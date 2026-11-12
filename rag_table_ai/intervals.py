"""Match numeric quantities against closed intervals in table cells."""

from __future__ import annotations

import re
from decimal import Decimal

_NUMBER = r"[+\-−]?(?:[0-9]{1,3}(?:,[0-9]{3}){1,21}|[0-9]{1,64})(?:\.[0-9]{1,64})?"
_CURRENCY_CODES = ("USD", "EUR", "GBP", "CNY", "JPY", "HKD", "CAD", "AUD", "CHF", "INR")
_PREFIX = rf"(?:[$¥€£]\s*|(?:{'|'.join(_CURRENCY_CODES)})\s+)"
_UNIT_PART = r"[A-Za-zµμ]+[²³]?"
_UNIT = rf"{_UNIT_PART}(?:/{_UNIT_PART})?|[A-Za-z]+\s+old|°[CF]|[\u4e00-\u9fff]+|%"
_QUANTITY = rf"(?:{_PREFIX})?{_NUMBER}(?:\s*(?:{_UNIT}))?"
_QUANTITY_RE = re.compile(
    rf"(?P<currency>{_PREFIX})?(?P<number>{_NUMBER})(?:\s*(?P<unit>{_UNIT}))?",
    re.IGNORECASE,
)
_RANGE_RE = re.compile(
    rf"(?P<low>{_QUANTITY})\s*[-–—~至到]\s*(?P<high>{_QUANTITY})",
    re.IGNORECASE,
)
_LABELED_RANGE_RE = re.compile(r"[^()]+\(([^()]+)\)")
_UNIT_ALIASES = {
    "周岁": "岁",
    "year": "岁",
    "years": "岁",
    "year old": "岁",
    "years old": "岁",
}


def _parse_quantity(text: str) -> tuple[int | Decimal, str] | None:
    match = _QUANTITY_RE.fullmatch(text.strip())
    if match is None:
        return None
    currency = (match["currency"] or "").strip().upper()
    suffix = " ".join((match["unit"] or "").split())
    if currency and suffix:
        return None
    if suffix.upper() in _CURRENCY_CODES:
        suffix = suffix.upper()
    unit = currency or _UNIT_ALIASES.get(suffix.lower(), suffix)
    number = match["number"].replace("−", "-").replace(",", "")
    if len(number.lstrip("+-").split(".", 1)[0]) > 64:
        return None
    return (Decimal(number) if "." in number else int(number), unit)


def _parse_range(text: str) -> tuple[int | Decimal, int | Decimal, str] | None:
    text = text.strip()
    labeled = _LABELED_RANGE_RE.fullmatch(text)
    if labeled:
        text = labeled[1].strip()
    text = re.sub(r"以上(?=\s*[至到])", "", text)
    match = _RANGE_RE.fullmatch(text)
    if match is None:
        return None
    left = _parse_quantity(match["low"])
    right = _parse_quantity(match["high"])
    if left is None or right is None:
        return None
    low, left_unit = left
    high, right_unit = right
    if low > high or (left_unit and right_unit and left_unit != right_unit):
        return None
    return low, high, left_unit or right_unit


def extract_range(text: str) -> tuple[int | Decimal, int | Decimal] | None:
    """Return ordered bounds for a supported closed interval."""
    parsed = _parse_range(text)
    return None if parsed is None else (parsed[0], parsed[1])


def match_interval(cell_text: str, query_text: str) -> bool:
    """Match a point to a range, or perform a literal match for text labels.

    Bare numbers inherit the range unit. Explicit units must agree after
    alias normalization. A query is a quantity, such as "15 kg", rather
    than a sentence from which this helper should extract a quantity.
    """
    cell = cell_text.strip()
    query = query_text.strip()
    if not cell or not query:
        return False

    bounds = _parse_range(cell)
    point = _parse_quantity(query)
    if bounds is not None:
        if point is None:
            return False
        low, high, unit = bounds
        value, query_unit = point
        return (not query_unit or query_unit == unit) and low <= value <= high

    cell_point = _parse_quantity(cell)
    if cell_point is not None or point is not None:
        return cell_point == point

    norm_cell = " ".join(cell.split())
    norm_query = " ".join(query.split())
    if norm_cell == norm_query:
        return True
    if any(char.isdecimal() for text in (cell, query) for char in text):
        return False
    return norm_cell.startswith(norm_query + " ")


def expand_interval_hint(cell_text: str, max_expanded: int = 12) -> str:
    """Append a bounded list of integer points for a short integer interval."""
    bounds = extract_range(cell_text)
    if bounds is None:
        return cell_text
    low, high = bounds
    if not isinstance(low, int) or not isinstance(high, int):
        return cell_text
    if 1 < high - low + 1 <= max_expanded:
        items = ", ".join(str(value) for value in range(low, high + 1))
        return f"{cell_text} [covers: {items}]"
    return cell_text
