"""Shared plumbing for outbound integrations: retries, idempotency, logging."""

from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.signing import sha256_hex
from app.models.audit import IntegrationLog
from app.models.enums import AuditAction, IntegrationStatus, IntegrationSystem
from app.services import audit


class IntegrationError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = True, status_code: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


def make_idempotency_key(system: IntegrationSystem, operation: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return f"{system}:{operation}:{sha256_hex(body)[:32]}"


class BaseConnector(ABC):
    """Template method: subclasses only implement `_perform`."""

    system: IntegrationSystem
    max_attempts: int = 3
    backoff_base: float = 0.2

    def __init__(self, db: Session, *, sandbox: bool = True) -> None:
        self.db = db
        self.sandbox = sandbox

    @abstractmethod
    async def _perform(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute the real call (or a sandbox simulation) and return a response."""

    async def execute(
        self,
        operation: str,
        payload: dict[str, Any],
        *,
        report_id: int | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[IntegrationLog, dict[str, Any]]:
        key = idempotency_key or make_idempotency_key(self.system, operation, payload)

        existing = self.db.execute(
            select(IntegrationLog).where(IntegrationLog.idempotency_key == key)
        ).scalar_one_or_none()
        if existing and existing.status == IntegrationStatus.SUCCESS:
            return existing, json.loads(existing.response_payload or "{}")

        log = existing or IntegrationLog(
            report_id=report_id,
            system=self.system,
            operation=operation,
            status=IntegrationStatus.PENDING,
            request_payload=json.dumps(payload, ensure_ascii=False, default=str),
            idempotency_key=key,
        )
        if existing is None:
            self.db.add(log)
        self.db.flush()

        started = time.perf_counter()
        last_error: Exception | None = None

        for attempt in range(1, self.max_attempts + 1):
            log.attempts = attempt
            try:
                response = await self._perform(operation, payload)
                log.status = IntegrationStatus.SUCCESS
                log.response_payload = json.dumps(response, ensure_ascii=False, default=str)
                log.external_reference = (
                    str(response.get("reference") or response.get("tracking_id") or response.get("id") or "") or None
                )
                log.error = None
                break
            except IntegrationError as exc:
                last_error = exc
                if not exc.retryable or attempt == self.max_attempts:
                    log.status = IntegrationStatus.FAILED
                    log.error = str(exc)
                    break
                log.status = IntegrationStatus.RETRYING
                self.db.flush()
                await asyncio.sleep(self.backoff_base * (2 ** (attempt - 1)))
            except Exception as exc:
                last_error = exc
                log.status = IntegrationStatus.FAILED
                log.error = str(exc)[:1000]
                break

        log.duration_ms = int((time.perf_counter() - started) * 1000)
        log.completed_at = datetime.now(UTC)
        self.db.flush()

        audit.record(
            self.db,
            action=AuditAction.INTEGRATION,
            entity_type="integration",
            entity_id=log.id,
            summary=f"{self.system}.{operation} -> {log.status}",
            after={
                "system": str(self.system),
                "operation": operation,
                "status": str(log.status),
                "attempts": log.attempts,
                "external_reference": log.external_reference,
                "duration_ms": log.duration_ms,
            },
            context={"report_id": report_id, "sandbox": self.sandbox},
        )

        if log.status != IntegrationStatus.SUCCESS:
            raise IntegrationError(f"{self.system}.{operation} failed: {last_error}", retryable=False)
        return log, json.loads(log.response_payload or "{}")

    async def _http_post(
        self, url: str, payload: dict[str, Any], headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                response = await client.post(url, json=payload, headers=headers or {})
            except httpx.RequestError as exc:
                raise IntegrationError(f"network error: {exc}", retryable=True) from exc
            if response.status_code >= 500:
                raise IntegrationError(
                    f"server error {response.status_code}",
                    retryable=True,
                    status_code=response.status_code,
                )
            if response.status_code >= 400:
                raise IntegrationError(
                    f"client error {response.status_code}: {response.text[:200]}",
                    retryable=False,
                    status_code=response.status_code,
                )
            return response.json()
