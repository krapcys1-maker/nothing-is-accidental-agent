"""Jedyny kontrakt kwot USD używany przez estymację, ledger i cache kosztów."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Iterable


USD_QUANTUM = Decimal("0.000001")


def decimal_from(value: object, *, label: str = "USD amount") -> Decimal:
    """Convert through ``str`` so binary floats never become Decimal inputs."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite numeric amount.") from exc
    if not amount.is_finite():
        raise ValueError(f"{label} must be a finite numeric amount.")
    return amount


def quantize_usd(value: object, *, label: str = "USD amount") -> Decimal:
    """Apply the project-wide financial boundary: Decimal(str(value)), 6dp, HALF_UP."""
    try:
        return decimal_from(value, label=label).quantize(USD_QUANTUM, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError(f"{label} cannot be represented at USD precision.") from exc


def sum_usd(values: Iterable[object], *, label: str = "USD amount") -> Decimal:
    """Sum exact decimal inputs first, then cross the six-decimal contract once."""
    total = sum((decimal_from(value, label=label) for value in values), Decimal("0"))
    return quantize_usd(total, label=label)


def usd_float(value: object, *, label: str = "USD amount") -> float:
    """Return the canonical Decimal amount at legacy float-facing boundaries."""
    return float(quantize_usd(value, label=label))
