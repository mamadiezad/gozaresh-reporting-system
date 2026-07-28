"""Iranian tax authority (سامانه مودیان) connector.

Builds a signed invoice envelope, submits it, and polls for the confirmation
status. In sandbox mode the exchange is simulated deterministically so demos
and CI runs never touch a real government endpoint.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.core.signing import sha256_hex, sign_payload
from app.integrations.base import BaseConnector, IntegrationError
from app.models.enums import IntegrationSystem
from app.models.report import Report
from app.utils.money import D, money_context, to_minor_units

TAX_RATE = "0.09"  # 9% VAT


class MoadianConnector(BaseConnector):
    system = IntegrationSystem.MOADIAN

    # ---- Envelope building ------------------------------------------
    @staticmethod
    def build_invoice(report: Report) -> dict[str, Any]:
        """Map an internal report onto the Moadian invoice schema (subset)."""
        issued = datetime.now(UTC)
        gross = D(report.total_payable or report.principal)
        taxable = to_minor_units(gross, report.currency)
        with money_context():
            vat = to_minor_units(gross * D(TAX_RATE), report.currency)
        return {
            "header": {
                "taxid": f"{settings.MOADIAN_MEMORY_ID}{issued:%y%m%d}{secrets.token_hex(4).upper()}",
                "indatim": int(issued.timestamp() * 1000),
                "inty": 1,  # invoice type: general
                "inp": 1,  # pattern: sale
                "ins": 1,  # subject: main
                "tins": settings.MOADIAN_ECONOMIC_CODE,
                "tob": 2,  # buyer type: legal entity
                "bid": report.counterparty or "UNKNOWN",
                "sindid": report.reference,
                "scln": report.department or "HQ",
                "tprdis": str(taxable),
                "tdis": "0",
                "tadis": str(taxable),
                "tvam": str(vat),
                "tbill": str(taxable + vat),
                "setm": 1,  # settlement: cash
                "cap": str(taxable + vat),
                "crn": report.currency,
                "ft": str(report.fx_rate) if report.fx_rate else "1",
            },
            "body": [
                {
                    "sstid": "2705010000000",  # service/goods code (demo)
                    "sstt": report.title[:100],
                    "am": "1",
                    "mu": "164",  # unit: service
                    "fee": str(taxable),
                    "prdis": str(taxable),
                    "dis": "0",
                    "adis": str(taxable),
                    "vra": TAX_RATE,
                    "vam": str(vat),
                    "tsstam": str(taxable + vat),
                }
            ],
            "payments": [],
        }

    # ---- Transport ----------------------------------------------------
    async def _perform(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        if operation == "submit_invoice":
            return await self._submit_invoice(payload)
        if operation == "inquiry":
            return await self._inquiry(payload)
        raise IntegrationError(f"Unknown Moadian operation {operation!r}", retryable=False)

    async def _submit_invoice(self, payload: dict[str, Any]) -> dict[str, Any]:
        signature = sign_payload("system-moadian", payload)
        envelope = {
            "packets": [
                {
                    "uid": payload["header"]["taxid"],
                    "packetType": "INVOICE.V01",
                    "retry": False,
                    "fiscalId": settings.MOADIAN_MEMORY_ID,
                    "dataSignature": signature["signature"],
                    "payload": payload,
                }
            ]
        }
        if self.sandbox:
            return {
                "sandbox": True,
                "reference": payload["header"]["taxid"],
                "uid": payload["header"]["taxid"],
                "status": "ACCEPTED",
                "confirmation_code": sha256_hex(payload["header"]["taxid"])[:16].upper(),
                "received_at": datetime.now(UTC).isoformat(),
                "signature_fingerprint": signature["public_key_fingerprint"],
            }
        return await self._http_post(
            f"{settings.MOADIAN_BASE_URL}/async/normal-enqueue",
            envelope,
            headers={
                "Authorization": f"Bearer {settings.MOADIAN_MEMORY_ID}",
                "Content-Type": "application/json",
            },
        )

    async def _inquiry(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = payload.get("uid")
        if not uid:
            raise IntegrationError("inquiry requires 'uid'", retryable=False)
        if self.sandbox:
            return {
                "sandbox": True,
                "reference": uid,
                "status": "SUCCESS",
                "confirmed_at": datetime.now(UTC).isoformat(),
            }
        return await self._http_post(
            f"{settings.MOADIAN_BASE_URL}/inquiry-by-reference-number",
            {"referenceNumber": uid},
            headers={"Authorization": f"Bearer {settings.MOADIAN_MEMORY_ID}"},
        )

    # ---- High-level helper ---------------------------------------------
    async def submit_report(self, report: Report) -> dict[str, Any]:
        invoice = self.build_invoice(report)
        _, response = await self.execute("submit_invoice", invoice, report_id=report.id)
        return response
