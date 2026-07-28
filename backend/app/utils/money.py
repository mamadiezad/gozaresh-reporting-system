"""High-precision Decimal helpers.

Every monetary computation runs inside a localcontext with 34 significant
digits and ROUND_HALF_EVEN (banker's rounding), then quantises to 16 decimal
places, matching the storage column Numeric(38, 16).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext

from app.core.config import settings

PLACES = settings.DECIMAL_PLACES
PRECISION = settings.DECIMAL_PRECISION
QUANT = Decimal(1).scaleb(-PLACES)  # 1e-16
ZERO = Decimal(0)

# Minor-unit exponents for display rounding (IRR/JPY are zero-decimal).
CURRENCY_EXPONENT: dict[str, int] = {
    "IRR": 0,
    "IRT": 0,
    "JPY": 0,
    "KRW": 0,
    "VND": 0,
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "AED": 2,
    "TRY": 2,
    "CNY": 2,
    "CAD": 2,
    "CHF": 2,
    "BHD": 3,
    "KWD": 3,
    "OMR": 3,
}


@contextmanager
def money_context() -> Iterator[None]:
    with localcontext() as ctx:
        ctx.prec = PRECISION
        ctx.rounding = ROUND_HALF_EVEN
        yield


def D(value: object) -> Decimal:
    """Safe Decimal constructor — never goes through binary float."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(repr(value))
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Cannot interpret {value!r} as a decimal amount") from exc


def q(value: object) -> Decimal:
    """Quantise to the canonical 16-decimal storage scale.

    The quantisation runs inside `money_context`, otherwise Python's default
    28-digit context raises InvalidOperation for large amounts: a rial figure
    with 14 integer digits plus 16 decimals needs 30 significant digits.
    """
    with money_context():
        return D(value).quantize(QUANT, rounding=ROUND_HALF_EVEN)


def to_minor_units(amount: object, currency: str) -> Decimal:
    """Round to the currency's real-world smallest unit (for display/payment)."""
    exponent = CURRENCY_EXPONENT.get(currency.upper(), 2)
    with money_context():
        return D(amount).quantize(Decimal(1).scaleb(-exponent), rounding=ROUND_HALF_EVEN)


def allocate(total: object, weights: list[Decimal]) -> list[Decimal]:
    """Split `total` across weights with zero cent loss (largest-remainder)."""
    total_d = q(total)
    weight_sum = sum(weights, ZERO)
    if weight_sum == 0:
        raise ValueError("Sum of weights must be non-zero")
    with money_context():
        raw = [total_d * w / weight_sum for w in weights]
        rounded = [q(r) for r in raw]
        drift = total_d - sum(rounded, ZERO)
        if drift != 0:
            idx = max(range(len(raw)), key=lambda i: raw[i] - rounded[i])
            rounded[idx] = q(rounded[idx] + drift)
    return rounded


def pct(value: object) -> Decimal:
    """Interpret 12.5 or '12.5%' as Decimal('0.125')."""
    if isinstance(value, str):
        value = value.strip().rstrip("%")
    return q(D(value) / Decimal(100))


def fmt(amount: object, currency: str = "IRR") -> str:
    minor = to_minor_units(amount, currency)
    exponent = CURRENCY_EXPONENT.get(currency.upper(), 2)
    return f"{minor:,.{exponent}f} {currency.upper()}"
