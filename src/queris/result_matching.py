"""Shared normalization and order-insensitive result matching."""

from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from typing import Any

NormalizedValue = tuple[str, Any]
NormalizedRow = tuple[NormalizedValue, ...]


def normalized_row_counts(rows: tuple[tuple[Any, ...], ...]) -> Counter[NormalizedRow]:
    """Normalize scalar representations and count rows without ordering."""
    return Counter(tuple(_normalize_value(value) for value in row) for row in rows)


def rows_match(
    actual_rows: tuple[tuple[Any, ...], ...],
    expected_rows: tuple[tuple[Any, ...], ...],
) -> bool:
    """Return whether two row collections match after scalar normalization."""
    return normalized_row_counts(actual_rows) == normalized_row_counts(expected_rows)


def _normalize_value(value: Any) -> NormalizedValue:
    if isinstance(value, bool) or value is None:
        return ("literal", value)
    if isinstance(value, (Decimal, int, float)):
        return ("number", Decimal(str(value)).normalize())
    if isinstance(value, (date, datetime)):
        return ("date", value.isoformat())
    return ("literal", value)
