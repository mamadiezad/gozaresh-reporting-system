"""Precision-safe monetary column type.

SQLite has no native DECIMAL: it maps NUMERIC to a C double, so
`Decimal("12500000000.1234567890123456")` comes back as
`12500000000.1234569549560547` — the 16-decimal guarantee is silently lost and
any signature covering that value stops verifying.

`Money` stores the value as a zero-padded, sign-aware **string** on SQLite (so
`ORDER BY` and range predicates still behave), and uses native NUMERIC(38, 16)
on PostgreSQL / MySQL where exact decimals are supported.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Numeric, String
from sqlalchemy.types import TypeDecorator

from app.utils.money import PLACES, money_context, q

# Enough room for 20 integer digits (IRR trillions) + 16 decimals.
_INT_DIGITS = 20
_WIDTH = _INT_DIGITS + 1 + PLACES  # digits + '.' + decimals
_OFFSET = Decimal(10) ** _INT_DIGITS  # shift so negatives sort correctly


class Money(TypeDecorator):
    """Exact Decimal storage across backends."""

    impl = Numeric(38, PLACES)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(_WIDTH + 2))
        return dialect.type_descriptor(Numeric(38, PLACES, asdecimal=True))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        value = q(value)
        if dialect.name != "sqlite":
            return value
        # Offset keeps lexicographic order == numeric order, including negatives.
        # The arithmetic must run in the wide money context: 21 integer digits
        # plus 16 decimals exceeds Python's default 28-digit precision.
        with money_context():
            shifted = value + _OFFSET
            if shifted < 0:
                raise ValueError(f"Amount {value} is below the supported range")
            text = f"{shifted:.{PLACES}f}"
        integer_part, _, decimal_part = text.partition(".")
        return f"{integer_part.rjust(_INT_DIGITS + 1, '0')}.{decimal_part}"

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if dialect.name != "sqlite":
            return q(value)
        with money_context():
            return q(Decimal(value) - _OFFSET)
