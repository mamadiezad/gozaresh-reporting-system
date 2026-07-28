"""Bank gateway connector: settlement requests, confirmations, IBAN checks."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.core.config import settings
from app.integrations.base import BaseConnector, IntegrationError
from app.models.enums import IntegrationSystem
from app.utils.money import D, to_minor_units


def validate_iban(iban: str) -> bool:
    """ISO 13616 mod-97 check (works for IR IBANs too)."""
    cleaned = iban.replace(" ", "").upper()
    if len(cleaned) < 15 or len(cleaned) > 34 or not cleaned[:2].isalpha():
        return False
    rearranged = cleaned[4:] + cleaned[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % 97 == 1


class BankConnector(BaseConnector):
    system = IntegrationSystem.BANK_GATEWAY

    def _sign_request(self, payload: dict[str, Any]) -> str:
        body = "&".join(f"{k}={payload[k]}" for k in sorted(payload))
        return hmac.new(settings.SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()

    async def _perform(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "settlement_request": self._settlement_request,
            "settlement_confirm": self._settlement_confirm,
            "balance_inquiry": self._balance_inquiry,
        }
        handler = handlers.get(operation)
        if handler is None:
            raise IntegrationError(f"Unknown bank operation {operation!r}", retryable=False)
        return await handler(payload)

    async def _settlement_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        iban = payload.get("iban", "")
        if iban and not validate_iban(iban):
            raise IntegrationError(f"Invalid IBAN checksum: {iban}", retryable=False)

        signed = {**payload, "terminal": settings.BANK_TERMINAL_ID}
        signed["signature"] = self._sign_request({k: v for k, v in signed.items() if k != "signature"})

        if self.sandbox:
            tracking = f"BNK{datetime.now(UTC):%Y%m%d}{secrets.token_hex(4).upper()}"
            return {
                "sandbox": True,
                "tracking_id": tracking,
                "reference": tracking,
                "status": "PENDING_CONFIRMATION",
                "amount": str(payload.get("amount")),
                "currency": payload.get("currency"),
                "requested_at": datetime.now(UTC).isoformat(),
            }
        return await self._http_post(f"{settings.BANK_GATEWAY_URL}/settlements", signed)

    async def _settlement_confirm(self, payload: dict[str, Any]) -> dict[str, Any]:
        tracking = payload.get("tracking_id")
        if not tracking:
            raise IntegrationError("settlement_confirm requires 'tracking_id'", retryable=False)
        if self.sandbox:
            return {
                "sandbox": True,
                "reference": tracking,
                "tracking_id": tracking,
                "status": "CONFIRMED",
                "bank_reference": f"RRN{secrets.token_hex(5).upper()}",
                "confirmed_at": datetime.now(UTC).isoformat(),
            }
        return await self._http_post(f"{settings.BANK_GATEWAY_URL}/settlements/{tracking}/confirm", payload)

    async def _balance_inquiry(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.sandbox:
            return {
                "sandbox": True,
                "reference": payload.get("account", "DEMO"),
                "available_balance": "12500000000",
                "currency": payload.get("currency", settings.BASE_CURRENCY),
                "as_of": datetime.now(UTC).isoformat(),
            }
        return await self._http_post(f"{settings.BANK_GATEWAY_URL}/accounts/balance", payload)

    # ---- High-level helpers ---------------------------------------------
    async def request_settlement(
        self,
        *,
        report_id: int,
        amount: Decimal | str,
        currency: str,
        iban: str = "",
        description: str = "",
    ) -> dict[str, Any]:
        payload = {
            "report_id": report_id,
            "amount": str(to_minor_units(D(amount), currency)),
            "currency": currency.upper(),
            "iban": iban,
            "description": description[:120],
        }
        _, response = await self.execute("settlement_request", payload, report_id=report_id)
        return response

    async def confirm_settlement(self, *, report_id: int, tracking_id: str) -> dict[str, Any]:
        _, response = await self.execute("settlement_confirm", {"tracking_id": tracking_id}, report_id=report_id)
        return response
