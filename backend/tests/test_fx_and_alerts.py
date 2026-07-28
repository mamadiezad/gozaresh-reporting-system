"""Features #1 (FX) and #3 (dashboard + alerts)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.enums import AlertKind, AlertSeverity, InstallmentStatus
from app.models.report import Installment, Report
from app.services import alerts as alerts_service
from app.services import fx


def _seed_owner(db):
    """Reports need a real creator row: SQLite enforces the FK."""
    from app.core.security import hash_password
    from app.models.enums import UserRole
    from app.models.user import User

    owner = User(
        username="fixture-owner",
        email="fixture-owner@gozaresh-demo.com",
        full_name="Fixture Owner",
        hashed_password=hash_password("TestPass!2024"),
        role=UserRole.REQUESTER,
    )
    db.add(owner)
    db.flush()
    return owner


class TestFxService:
    @pytest.mark.asyncio
    async def test_identity_rate(self):
        quote = await fx.get_rate("USD", "USD")
        assert quote.rate == Decimal(1)
        assert quote.source == "identity"

    @pytest.mark.asyncio
    async def test_cross_rate_is_consistent(self):
        fx.clear_cache()
        usd_eur = (await fx.get_rate("USD", "EUR")).rate
        eur_usd = (await fx.get_rate("EUR", "USD")).rate
        product = usd_eur * eur_usd
        assert abs(product - Decimal(1)) < Decimal("0.0000000001")

    @pytest.mark.asyncio
    async def test_conversion_precision(self):
        fx.clear_cache()
        amount, quote = await fx.convert("1000", "USD", "IRR")
        assert amount == Decimal(587500000).quantize(Decimal("1E-16"))
        assert quote.source == "offline_fixture"

    @pytest.mark.asyncio
    async def test_unsupported_currency_raises(self):
        fx.clear_cache()
        with pytest.raises(fx.FxError):
            await fx.get_rate("USD", "XXX")

    @pytest.mark.asyncio
    async def test_cache_is_faster_on_second_hit(self):
        fx.clear_cache()
        first = await fx.get_rate("USD", "GBP")
        second = await fx.get_rate("USD", "GBP")
        assert second.latency_ms <= first.latency_ms + 1.0

    def test_api_rate_endpoint(self, client, auth):
        response = client.get("/api/v1/calculations/rates/USD/IRR", headers=auth("requester"))
        assert response.status_code == 200
        body = response.json()
        assert Decimal(body["rate"]) > 0
        assert body["base"] == "USD" and body["quote"] == "IRR"

    def test_api_convert_endpoint(self, client, auth):
        response = client.post(
            "/api/v1/calculations/convert",
            json={"amount": "100", "base": "EUR", "quote": "USD"},
            headers=auth("requester"),
        )
        assert response.status_code == 200
        assert Decimal(response.json()["converted_amount"]) > Decimal(100)


class TestCalculationApi:
    def test_preview_reports_sla(self, client, auth):
        response = client.post(
            "/api/v1/calculations/preview",
            json={
                "principal": "5000000000",
                "annual_rate_percent": "23.5",
                "term_months": 36,
                "currency": "IRR",
            },
            headers=auth("requester"),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["within_sla"] is True
        assert body["duration_ms"] < 50
        assert len(body["schedule"]) == 36
        assert response.headers["X-Calc-SLA-Met"] == "true"

    def test_preview_with_currency_conversion(self, client, auth):
        response = client.post(
            "/api/v1/calculations/preview",
            json={
                "principal": "10000",
                "annual_rate_percent": "6",
                "term_months": 12,
                "currency": "USD",
                "convert_to": "IRR",
            },
            headers=auth("requester"),
        )
        body = response.json()
        assert body["fx_rate"] is not None
        assert body["base_currency"] == "IRR"
        assert Decimal(body["amount_in_base"]) > Decimal(body["total_payable"])

    def test_rejects_negative_principal(self, client, auth):
        response = client.post(
            "/api/v1/calculations/preview",
            json={"principal": "-100", "annual_rate_percent": "5", "term_months": 12},
            headers=auth("requester"),
        )
        assert response.status_code == 422

    def test_benchmark_endpoint(self, client, auth):
        response = client.get(
            "/api/v1/calculations/benchmark",
            params={"iterations": 50},
            headers=auth("requester"),
        )
        body = response.json()
        assert body["p99_ms"] <= body["sla_ms"]
        assert body["sla_met_ratio"] == 1.0


class TestAlerts:
    def test_out_of_range_transaction_is_flagged(self, client, auth):
        response = client.post(
            "/api/v1/reports",
            json={
                "title": "Very large facility",
                "principal": "99000000000000",  # far above the IRR limit
                "currency": "IRR",
                "annual_rate_percent": "20",
                "term_months": 12,
            },
            headers=auth("requester"),
        )
        assert response.status_code == 201
        alerts = client.get("/api/v1/alerts", headers=auth("finance_manager")).json()
        assert any(a["kind"] == "out_of_range_transaction" for a in alerts)
        assert any(a["severity"] == "critical" for a in alerts)

    def test_normal_transaction_raises_no_range_alert(self, client, auth, sample_report):
        alerts = client.get("/api/v1/alerts", headers=auth("finance_manager")).json()
        assert not any(a["kind"] == "out_of_range_transaction" for a in alerts)

    def test_overdue_detection(self, db):
        owner = _seed_owner(db)
        report = Report(
            reference="GZR-TEST-001",
            title="Overdue test",
            principal=Decimal(1000000),
            currency="IRR",
            annual_rate=Decimal("0.18"),
            term_months=3,
            created_by_id=owner.id,
            total_payable=Decimal(1050000),
        )
        db.add(report)
        db.flush()
        db.add(
            Installment(
                report_id=report.id,
                number=1,
                due_date=date.today() - timedelta(days=45),
                amount=Decimal(350000),
                principal_component=Decimal(330000),
                interest_component=Decimal(20000),
                remaining_balance=Decimal(700000),
                status=InstallmentStatus.SCHEDULED,
            )
        )
        db.flush()

        created = alerts_service.scan_overdue_installments(db)
        assert len(created) == 1
        assert created[0].kind == AlertKind.OVERDUE_INSTALLMENT
        assert created[0].severity == AlertSeverity.CRITICAL  # >30 days late

    def test_overdue_scan_is_idempotent(self, db):
        owner = _seed_owner(db)
        report = Report(
            reference="GZR-TEST-002",
            title="Dedupe test",
            principal=Decimal(500000),
            currency="IRR",
            annual_rate=Decimal("0.1"),
            term_months=1,
            created_by_id=owner.id,
            total_payable=Decimal(505000),
        )
        db.add(report)
        db.flush()
        db.add(
            Installment(
                report_id=report.id,
                number=1,
                due_date=date.today() - timedelta(days=3),
                amount=Decimal(505000),
                principal_component=Decimal(500000),
                interest_component=Decimal(5000),
                remaining_balance=Decimal(0),
            )
        )
        db.flush()

        assert len(alerts_service.scan_overdue_installments(db)) == 1
        assert len(alerts_service.scan_overdue_installments(db)) == 0  # deduped

    def test_acknowledge_alert(self, client, auth):
        client.post(
            "/api/v1/reports",
            json={
                "title": "Huge",
                "principal": "99000000000000",
                "currency": "IRR",
                "annual_rate_percent": "20",
                "term_months": 6,
            },
            headers=auth("requester"),
        )
        alert_id = client.get("/api/v1/alerts", headers=auth("inspector")).json()[0]["id"]
        response = client.post(f"/api/v1/alerts/{alert_id}/acknowledge", headers=auth("inspector"))
        assert response.status_code == 200
        assert response.json()["acknowledged"] is True

    def test_scan_endpoint(self, client, auth, sample_report):
        response = client.post("/api/v1/alerts/scan", headers=auth("admin"))
        assert response.status_code == 200
        assert "total" in response.json()


class TestDashboard:
    def test_overview_shape(self, client, auth, sample_report):
        body = client.get("/api/v1/dashboard/overview", headers=auth("finance_manager")).json()
        for key in (
            "kpis",
            "status_breakdown",
            "currency_exposure",
            "monthly_trend",
            "workflow_throughput",
            "upcoming_installments",
            "integration_health",
            "alerts",
        ):
            assert key in body

    def test_kpis_track_lifecycle(self, client, auth, sample_report):
        rid = sample_report["id"]
        before = client.get("/api/v1/dashboard/kpis", headers=auth("ceo")).json()
        assert before["total_reports"] == 1
        assert before["approved"] == 0

        client.post(f"/api/v1/reports/{rid}/submit", headers=auth("requester"))
        for role in ("finance_manager", "inspector", "ceo"):
            client.post(
                f"/api/v1/reports/{rid}/decision",
                json={"approved": True, "comment": ""},
                headers=auth(role),
            )

        after = client.get("/api/v1/dashboard/kpis", headers=auth("ceo")).json()
        assert after["approved"] == 1
        assert Decimal(after["approval_rate_percent"]) == Decimal(100).quantize(Decimal("1E-16"))

    def test_currency_exposure(self, client, auth, sample_report):
        client.post(
            "/api/v1/reports",
            json={
                "title": "USD facility",
                "principal": "50000",
                "currency": "USD",
                "annual_rate_percent": "7",
                "term_months": 24,
            },
            headers=auth("requester"),
        )
        exposure = client.get("/api/v1/dashboard/charts/currency", headers=auth("finance_manager")).json()
        assert {row["currency"] for row in exposure} == {"IRR", "USD"}

    def test_upcoming_installments(self, client, auth, sample_report):
        upcoming = client.get(
            "/api/v1/dashboard/upcoming",
            params={"days": 45},
            headers=auth("finance_manager"),
        ).json()
        assert len(upcoming) >= 1
        assert upcoming[0]["days_until"] >= 0
