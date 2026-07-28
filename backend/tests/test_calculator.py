"""Feature #1 — precise, fast, multi-currency calculations."""

from __future__ import annotations

import time
from datetime import date
from decimal import Decimal

import pytest

from app.core.config import settings
from app.services.calculator import (
    CalculationError,
    annuity_payment,
    build_amortisation_schedule,
    calculate,
    compound_interest,
    effective_annual_rate,
)
from app.utils.money import D, allocate, q, to_minor_units


class TestDecimalPrecision:
    def test_no_float_contamination(self):
        result = calculate(principal="0.1", annual_rate_percent="0", term_months=3, currency="USD")
        total = sum(row.principal_component for row in result.schedule)
        assert total == Decimal("0.1000000000000000")

    def test_sixteen_decimal_places_retained(self):
        fv, interest = compound_interest("1", "0.07", "1", 365)
        assert fv.as_tuple().exponent == -settings.DECIMAL_PLACES
        assert interest > Decimal("0.0725")  # ~7.25% continuous-ish
        assert interest < Decimal("0.0726")

    def test_schedule_closes_exactly(self):
        schedule, total_interest, _ = build_amortisation_schedule("1000000000", Decimal("0.18"), 24, date(2026, 1, 1))
        principal_sum = sum(row.principal_component for row in schedule)
        interest_sum = sum(row.interest_component for row in schedule)
        assert principal_sum == Decimal(1000000000).quantize(Decimal("1E-16"))
        assert interest_sum == total_interest
        assert schedule[-1].remaining_balance == 0

    def test_allocate_has_no_rounding_loss(self):
        parts = allocate("100", [Decimal(1), Decimal(1), Decimal(1)])
        assert sum(parts) == q("100")

    def test_known_annuity_value(self):
        # 100,000 @ 12% nominal over 12 monthly payments -> 8,884.879...
        payment = annuity_payment("100000", Decimal("0.12"), 12)
        assert Decimal("8884.87") < payment < Decimal("8884.89")

    def test_effective_annual_rate(self):
        # 12% nominal compounded monthly -> 12.6825% effective
        ear = effective_annual_rate(Decimal("0.12"), 12)
        assert Decimal("0.1268") < ear < Decimal("0.1269")

    def test_zero_rate_is_linear(self):
        result = calculate(principal="120000", annual_rate_percent="0", term_months=12, currency="USD")
        assert result.total_interest == 0
        assert result.periodic_payment == q("10000")


class TestSLA:
    @pytest.mark.parametrize("term", [12, 60, 120, 360])
    def test_within_50ms(self, term):
        result = calculate(
            principal="9876543210",
            annual_rate_percent="23.75",
            term_months=term,
            currency="IRR",
        )
        assert result.within_sla, f"{term}m took {result.duration_ms:.2f} ms (SLA {settings.CALC_SLA_MS} ms)"

    def test_p99_under_sla_over_200_runs(self):
        durations = []
        for _ in range(200):
            started = time.perf_counter()
            calculate(
                principal="5000000000",
                annual_rate_percent="21",
                term_months=60,
                currency="IRR",
            )
            durations.append((time.perf_counter() - started) * 1000)
        durations.sort()
        p99 = durations[int(len(durations) * 0.99)]
        assert p99 <= settings.CALC_SLA_MS, f"p99={p99:.2f} ms"


class TestValidation:
    def test_rejects_zero_principal(self):
        with pytest.raises(CalculationError):
            calculate(principal="0", annual_rate_percent="10", term_months=12)

    def test_rejects_negative_term(self):
        with pytest.raises(CalculationError):
            calculate(principal="1000", annual_rate_percent="10", term_months=-1)

    def test_rejects_invalid_compounding(self):
        with pytest.raises(CalculationError):
            compound_interest("1000", "0.1", "1", 0)


class TestCurrencyRounding:
    @pytest.mark.parametrize(
        "currency,amount,expected",
        [
            ("IRR", "1234.6", "1235"),
            ("USD", "1234.567", "1234.57"),
            ("KWD", "1234.5678", "1234.568"),
            ("JPY", "99.5", "100"),  # banker's rounding to even
            ("JPY", "98.5", "98"),
        ],
    )
    def test_minor_units(self, currency, amount, expected):
        assert to_minor_units(D(amount), currency) == Decimal(expected)


class TestQuarterlySchedule:
    def test_quarterly_frequency(self):
        schedule, _, _ = build_amortisation_schedule("1200000", Decimal("0.16"), 24, date(2026, 1, 15), "quarterly")
        assert len(schedule) == 8
        assert schedule[0].due_date == date(2026, 4, 15)
        assert sum(r.principal_component for r in schedule) == q("1200000")

    def test_month_end_clamping(self):
        schedule, _, _ = build_amortisation_schedule("120000", Decimal("0.1"), 3, date(2026, 1, 31))
        assert schedule[0].due_date == date(2026, 2, 28)


class TestStoragePrecision:
    """Regression guard: SQLite maps NUMERIC to a C double, which silently
    destroyed the 16-decimal guarantee and broke signature verification.
    The custom `Money` type stores exact decimals on every backend."""

    @pytest.mark.parametrize(
        "amount",
        [
            "12500000000.1234567890123456",
            "0.0000000000000001",
            "99000000000000.9999999999999999",
            "1",
        ],
    )
    def test_decimal_survives_roundtrip(self, db, amount):
        from app.core.security import hash_password
        from app.models.report import Report
        from app.models.user import User

        owner = User(
            username=f"precision-{amount[:6]}",
            email=f"precision-{abs(hash(amount))}@gozaresh-demo.com",
            hashed_password=hash_password("TestPass!2024"),
            role="requester",
        )
        db.add(owner)
        db.flush()

        report = Report(
            reference=f"PREC-{amount[:8]}",
            title="precision probe",
            principal=Decimal(amount),
            currency="IRR",
            annual_rate=Decimal("0.1"),
            term_months=1,
            created_by_id=owner.id,
        )
        db.add(report)
        db.commit()
        db.expire_all()

        stored = db.get(Report, report.id).principal
        assert stored == Decimal(amount), f"{amount} came back as {stored}"

    def test_ordering_is_numeric(self, db):
        from sqlalchemy import select

        from app.core.security import hash_password
        from app.models.report import Report
        from app.models.user import User

        owner = User(
            username="order-probe",
            email="order-probe@gozaresh-demo.com",
            hashed_password=hash_password("TestPass!2024"),
            role="requester",
        )
        db.add(owner)
        db.flush()

        for index, amount in enumerate(["1000000000", "5", "250000", "0.5"]):
            db.add(
                Report(
                    reference=f"ORD-{index}",
                    title="ordering probe",
                    principal=Decimal(amount),
                    currency="IRR",
                    annual_rate=Decimal(0),
                    term_months=1,
                    created_by_id=owner.id,
                )
            )
        db.commit()

        ordered = db.execute(select(Report.principal).order_by(Report.principal.asc())).scalars().all()
        assert ordered == sorted(ordered)
        assert ordered[0] == Decimal("0.5")
        assert ordered[-1] == Decimal(1000000000)
