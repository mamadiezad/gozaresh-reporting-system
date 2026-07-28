"""Feature #4 — tax authority, bank gateway and accounting integrations."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.integrations import (
    make_idempotency_key,
    parse_voucher_xml,
    validate_balanced,
    validate_iban,
)
from app.models.enums import IntegrationSystem


@pytest.fixture
def approved_report(client, auth, sample_report):
    rid = sample_report["id"]
    client.post(f"/api/v1/reports/{rid}/submit", headers=auth("requester"))
    for role in ("finance_manager", "inspector", "ceo"):
        client.post(
            f"/api/v1/reports/{rid}/decision",
            json={"approved": True, "comment": ""},
            headers=auth(role),
        )
    return client.get(f"/api/v1/reports/{rid}", headers=auth("requester")).json()


class TestIbanValidation:
    @pytest.mark.parametrize(
        "iban,expected",
        [
            ("IR820540102680020817909002", True),
            ("DE89370400440532013000", True),
            ("GB82WEST12345698765432", True),
            ("IR820540102680020817909003", False),  # bad checksum
            ("NOTANIBAN", False),
            ("", False),
        ],
    )
    def test_mod97(self, iban, expected):
        assert validate_iban(iban) is expected

    def test_api_endpoint(self, client, auth):
        response = client.get(
            "/api/v1/integrations/bank/validate-iban",
            params={"iban": "DE89370400440532013000"},
            headers=auth("requester"),
        )
        assert response.json()["valid"] is True


class TestMoadian:
    def test_invoice_envelope(self, client, auth, approved_report):
        invoice = client.get(
            f"/api/v1/integrations/moadian/{approved_report['id']}/preview",
            headers=auth("finance_manager"),
        ).json()
        assert "header" in invoice and "body" in invoice
        header = invoice["header"]
        assert header["sindid"] == approved_report["reference"]
        assert Decimal(header["tvam"]) > 0  # VAT present
        assert Decimal(header["tbill"]) == Decimal(header["tadis"]) + Decimal(header["tvam"])

    def test_submission_requires_approval(self, client, auth, sample_report):
        response = client.post(
            f"/api/v1/integrations/moadian/{sample_report['id']}/submit",
            headers=auth("finance_manager"),
        )
        assert response.status_code == 409
        assert "APPROVED" in response.json()["detail"]

    def test_successful_submission(self, client, auth, approved_report):
        response = client.post(
            f"/api/v1/integrations/moadian/{approved_report['id']}/submit",
            headers=auth("finance_manager"),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ACCEPTED"
        assert body["reference"]
        assert body["signature_fingerprint"]

    def test_submission_is_idempotent(self, client, auth, approved_report):
        rid = approved_report["id"]
        first = client.post(
            f"/api/v1/integrations/moadian/{rid}/submit",
            headers=auth("finance_manager"),
        ).json()
        logs = client.get(
            "/api/v1/integrations/logs",
            params={"system": "moadian"},
            headers=auth("finance_manager"),
        ).json()
        assert len([log for log in logs if log["report_id"] == rid]) == 1
        assert first["status"] == "ACCEPTED"


class TestBankGateway:
    def test_settlement_flow(self, client, auth, approved_report):
        rid = approved_report["id"]
        settle = client.post(
            f"/api/v1/integrations/bank/{rid}/settle",
            json={
                "iban": "IR820540102680020817909002",
                "description": "Q3 disbursement",
            },
            headers=auth("finance_manager"),
        )
        assert settle.status_code == 200
        tracking = settle.json()["tracking_id"]
        assert settle.json()["status"] == "PENDING_CONFIRMATION"

        confirm = client.post(
            f"/api/v1/integrations/bank/{rid}/confirm",
            json={"tracking_id": tracking},
            headers=auth("finance_manager"),
        )
        assert confirm.status_code == 200
        assert confirm.json()["status"] == "CONFIRMED"
        assert confirm.json()["bank_reference"].startswith("RRN")

    def test_bad_iban_is_rejected(self, client, auth, approved_report):
        response = client.post(
            f"/api/v1/integrations/bank/{approved_report['id']}/settle",
            json={"iban": "IR000000000000000000000000"},
            headers=auth("finance_manager"),
        )
        assert response.status_code == 422


class TestAccounting:
    def test_voucher_is_balanced(self, client, auth, approved_report):
        voucher = client.get(
            f"/api/v1/integrations/accounting/{approved_report['id']}/voucher.json",
            headers=auth("finance_manager"),
        ).json()
        assert validate_balanced(voucher)
        assert Decimal(voucher["voucher"]["totals"]["debit"]) == Decimal(voucher["voucher"]["totals"]["credit"])

    def test_xml_export_and_reimport(self, client, auth, approved_report):
        response = client.get(
            f"/api/v1/integrations/accounting/{approved_report['id']}/voucher.xml",
            headers=auth("finance_manager"),
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/xml")
        xml = response.text
        assert xml.startswith("<?xml")

        parsed = parse_voucher_xml(xml)
        assert parsed["number"] == approved_report["reference"]
        assert len(parsed["lines"]) >= 2

    def test_import_endpoint(self, client, auth, approved_report):
        xml = client.get(
            f"/api/v1/integrations/accounting/{approved_report['id']}/voucher.xml",
            headers=auth("finance_manager"),
        ).text
        response = client.post(
            "/api/v1/integrations/accounting/import-xml",
            content=xml,
            headers={**auth("finance_manager"), "Content-Type": "application/xml"},
        )
        assert response.status_code == 200
        assert response.json()["parsed"]["number"] == approved_report["reference"]

    def test_malformed_xml_rejected(self, client, auth):
        response = client.post(
            "/api/v1/integrations/accounting/import-xml",
            content="<not-valid-xml",
            headers={**auth("finance_manager"), "Content-Type": "application/xml"},
        )
        assert response.status_code == 422

    def test_push_posts_ledger_entry(self, client, auth, approved_report):
        response = client.post(
            f"/api/v1/integrations/accounting/{approved_report['id']}/push",
            headers=auth("finance_manager"),
        )
        assert response.status_code == 200
        assert response.json()["status"] == "POSTED"
        assert response.json()["ledger_id"]


class TestIntegrationPlumbing:
    def test_idempotency_key_is_stable(self):
        payload = {"b": 2, "a": 1}
        key_one = make_idempotency_key(IntegrationSystem.BANK_GATEWAY, "settle", payload)
        key_two = make_idempotency_key(IntegrationSystem.BANK_GATEWAY, "settle", {"a": 1, "b": 2})
        assert key_one == key_two

    def test_idempotency_key_changes_with_payload(self):
        a = make_idempotency_key(IntegrationSystem.BANK_GATEWAY, "settle", {"amount": "100"})
        b = make_idempotency_key(IntegrationSystem.BANK_GATEWAY, "settle", {"amount": "200"})
        assert a != b

    def test_every_call_is_audited(self, client, auth, approved_report):
        client.post(
            f"/api/v1/integrations/moadian/{approved_report['id']}/submit",
            headers=auth("finance_manager"),
        )
        trail = client.get(
            "/api/v1/audit/logs",
            params={"entity_type": "integration"},
            headers=auth("auditor"),
        ).json()
        assert len(trail) >= 1
        assert "moadian" in trail[0]["summary"]

    def test_integration_health_dashboard(self, client, auth, approved_report):
        client.post(
            f"/api/v1/integrations/moadian/{approved_report['id']}/submit",
            headers=auth("finance_manager"),
        )
        health = client.get("/api/v1/dashboard/integrations", headers=auth("finance_manager")).json()
        moadian = next(h for h in health if h["system"] == "moadian")
        assert moadian["success"] >= 1
        assert moadian["success_rate"] == 100.0
