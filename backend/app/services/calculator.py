"""Financial engine: compound interest, amortisation, FX conversion.

Design goals
------------
* Pure Decimal arithmetic (no float anywhere on the money path).
* 16 decimal places of retained precision, banker's rounding.
* Deterministic and side-effect free -> trivially unit-testable.
* Every public entry point reports its own wall-clock duration so the
  50 ms SLA can be asserted in tests and surfaced in the API response.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from app.core.config import settings
from app.utils.money import ZERO, D, money_context, q, to_minor_units

Frequency = Literal["monthly", "quarterly", "semiannual", "annual"]
FREQUENCY_PER_YEAR: dict[Frequency, int] = {
    "monthly": 12,
    "quarterly": 4,
    "semiannual": 2,
    "annual": 1,
}


class CalculationError(ValueError):
    """Invalid financial inputs."""


# --------------------------------------------------------------------------
# Result containers
# --------------------------------------------------------------------------
@dataclass(slots=True)
class InstallmentRow:
    number: int
    due_date: date
    amount: Decimal
    principal_component: Decimal
    interest_component: Decimal
    remaining_balance: Decimal

    def as_dict(self) -> dict:
        return {
            "number": self.number,
            "due_date": self.due_date.isoformat(),
            "amount": str(self.amount),
            "principal_component": str(self.principal_component),
            "interest_component": str(self.interest_component),
            "remaining_balance": str(self.remaining_balance),
        }


@dataclass(slots=True)
class CalculationResult:
    principal: Decimal
    currency: str
    annual_rate: Decimal
    term_months: int
    compounding_per_year: int
    total_interest: Decimal
    total_payable: Decimal
    periodic_payment: Decimal
    effective_annual_rate: Decimal
    schedule: list[InstallmentRow] = field(default_factory=list)
    fx_rate: Decimal | None = None
    base_currency: str | None = None
    amount_in_base: Decimal | None = None
    fx_source: str | None = None
    duration_ms: float = 0.0

    @property
    def within_sla(self) -> bool:
        return self.duration_ms <= settings.CALC_SLA_MS

    def as_dict(self, *, include_schedule: bool = True) -> dict:
        data = {
            "principal": str(self.principal),
            "currency": self.currency,
            "annual_rate": str(self.annual_rate),
            "term_months": self.term_months,
            "compounding_per_year": self.compounding_per_year,
            "total_interest": str(self.total_interest),
            "total_payable": str(self.total_payable),
            "periodic_payment": str(self.periodic_payment),
            "effective_annual_rate": str(self.effective_annual_rate),
            "display_total": str(to_minor_units(self.total_payable, self.currency)),
            "fx_rate": str(self.fx_rate) if self.fx_rate is not None else None,
            "base_currency": self.base_currency,
            "amount_in_base": str(self.amount_in_base) if self.amount_in_base is not None else None,
            "fx_source": self.fx_source,
            "duration_ms": round(self.duration_ms, 4),
            "within_sla": self.within_sla,
            "sla_ms": settings.CALC_SLA_MS,
        }
        if include_schedule:
            data["schedule"] = [row.as_dict() for row in self.schedule]
        return data


# --------------------------------------------------------------------------
# Core maths
# --------------------------------------------------------------------------
def _pow_decimal(base: Decimal, exponent: int) -> Decimal:
    """Exact integer exponentiation by squaring — avoids float `**`."""
    if exponent < 0:
        return Decimal(1) / _pow_decimal(base, -exponent)
    result, acc, e = Decimal(1), base, exponent
    while e:
        if e & 1:
            result *= acc
        acc *= acc
        e >>= 1
    return result


def compound_interest(
    principal: Decimal | str | int,
    annual_rate: Decimal | str | float,
    years: Decimal | str | float,
    compounding_per_year: int = 12,
) -> tuple[Decimal, Decimal]:
    """Return (future_value, interest). Rate is a fraction, e.g. 0.18 for 18%."""
    p, r = D(principal), D(annual_rate)
    y = D(years)
    if p < 0:
        raise CalculationError("Principal must be non-negative")
    if compounding_per_year <= 0:
        raise CalculationError("compounding_per_year must be positive")
    if y < 0:
        raise CalculationError("years must be non-negative")

    with money_context():
        n = Decimal(compounding_per_year)
        periods_exact = n * y
        periods_int = int(periods_exact)
        growth = _pow_decimal(Decimal(1) + r / n, periods_int)
        remainder = periods_exact - periods_int
        if remainder != 0:  # fractional period -> exp/ln continuation
            growth *= ((Decimal(1) + r / n).ln() * remainder).exp()
        future_value = p * growth
    return q(future_value), q(future_value - p)


def effective_annual_rate(annual_rate: Decimal | str | float, compounding_per_year: int = 12) -> Decimal:
    """EAR = (1 + r/n)^n - 1."""
    r = D(annual_rate)
    with money_context():
        n = Decimal(compounding_per_year)
        return q(_pow_decimal(Decimal(1) + r / n, compounding_per_year) - Decimal(1))


def annuity_payment(
    principal: Decimal | str | int,
    annual_rate: Decimal | str | float,
    term_months: int,
    payments_per_year: int = 12,
) -> Decimal:
    """Standard amortising payment  A = P·i / (1 - (1+i)^-n)."""
    p, r = D(principal), D(annual_rate)
    if term_months <= 0:
        raise CalculationError("term_months must be positive")
    with money_context():
        periods = max(1, int(Decimal(term_months) * Decimal(payments_per_year) / Decimal(12)))
        if r == 0:
            return q(p / Decimal(periods))
        i = r / Decimal(payments_per_year)
        discount = Decimal(1) - _pow_decimal(Decimal(1) + i, -periods)
        return q(p * i / discount)


def _add_months(anchor: date, months: int) -> date:
    """Month arithmetic that clamps to the end of shorter months."""
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    next_month_first = date(year + (month // 12), (month % 12) + 1, 1)
    last_day = (next_month_first - timedelta(days=1)).day
    return date(year, month, min(anchor.day, last_day))


def build_amortisation_schedule(
    principal: Decimal | str | int,
    annual_rate: Decimal | str | float,
    term_months: int,
    start_date: date,
    frequency: Frequency = "monthly",
) -> tuple[list[InstallmentRow], Decimal, Decimal]:
    """Return (schedule, total_interest, periodic_payment) with exact closure.

    The final row absorbs accumulated rounding drift so that the sum of the
    principal components equals the original principal to the last of the
    16 decimal places.
    """
    p, r = D(principal), D(annual_rate)
    per_year = FREQUENCY_PER_YEAR[frequency]
    step_months = 12 // per_year
    periods = max(1, term_months // step_months)

    payment = annuity_payment(p, r, term_months, per_year)
    schedule: list[InstallmentRow] = []

    with money_context():
        i = r / Decimal(per_year)
        balance = p
        total_interest = ZERO
        for n in range(1, periods + 1):
            interest = q(balance * i)
            if n == periods:  # closing row: settle whatever is left
                principal_part = q(balance)
                amount = q(principal_part + interest)
            else:
                principal_part = q(payment - interest)
                amount = payment
            balance = q(balance - principal_part)
            total_interest = q(total_interest + interest)
            schedule.append(
                InstallmentRow(
                    number=n,
                    due_date=_add_months(start_date, n * step_months),
                    amount=amount,
                    principal_component=principal_part,
                    interest_component=interest,
                    remaining_balance=balance if balance > 0 else ZERO,
                )
            )
    return schedule, total_interest, payment


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------
def calculate(
    *,
    principal: Decimal | str | int,
    annual_rate_percent: Decimal | str | float,
    term_months: int,
    compounding_per_year: int = 12,
    currency: str = "IRR",
    start_date: date | None = None,
    frequency: Frequency = "monthly",
    fx_rate: Decimal | None = None,
    base_currency: str | None = None,
    fx_source: str | None = None,
    with_schedule: bool = True,
) -> CalculationResult:
    """One-shot computation of interest, schedule and base-currency amount."""
    started = time.perf_counter()

    p = D(principal)
    if p <= 0:
        raise CalculationError("Principal must be greater than zero")
    if term_months < 0:
        raise CalculationError("term_months must be non-negative")

    rate = q(D(annual_rate_percent) / Decimal(100))
    start = start_date or date.today()

    if term_months == 0 or not with_schedule:
        years = D(term_months) / Decimal(12)
        future_value, interest = compound_interest(p, rate, years, compounding_per_year)
        schedule: list[InstallmentRow] = []
        payment = ZERO if term_months == 0 else q(future_value / Decimal(term_months))
        total_payable = future_value
    else:
        schedule, interest, payment = build_amortisation_schedule(p, rate, term_months, start, frequency)
        with money_context():
            total_payable = q(sum((row.amount for row in schedule), ZERO))

    ear = effective_annual_rate(rate, compounding_per_year)

    amount_in_base = None
    if fx_rate is not None:
        with money_context():
            amount_in_base = q(total_payable * D(fx_rate))

    result = CalculationResult(
        principal=q(p),
        currency=currency.upper(),
        annual_rate=rate,
        term_months=term_months,
        compounding_per_year=compounding_per_year,
        total_interest=interest,
        total_payable=total_payable,
        periodic_payment=payment,
        effective_annual_rate=ear,
        schedule=schedule,
        fx_rate=D(fx_rate) if fx_rate is not None else None,
        base_currency=(base_currency or settings.BASE_CURRENCY).upper() if fx_rate is not None else None,
        amount_in_base=amount_in_base,
        fx_source=fx_source,
    )
    result.duration_ms = (time.perf_counter() - started) * 1000
    return result
