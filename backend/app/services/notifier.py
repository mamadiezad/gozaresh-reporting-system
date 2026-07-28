"""Multi-channel notification fan-out: email, SMS and live WebSocket."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.audit import Notification
from app.models.enums import NotificationChannel, NotificationStatus

logger = logging.getLogger("gozaresh.notifier")


# --------------------------------------------------------------------------
# WebSocket hub
# --------------------------------------------------------------------------
class ConnectionManager:
    """Tracks live dashboard sockets and broadcasts events by topic."""

    def __init__(self) -> None:
        self._connections: dict[str, set[Any]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, websocket: Any, topic: str = "dashboard") -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[topic].add(websocket)
        logger.info("ws connected topic=%s total=%d", topic, self.count(topic))

    async def disconnect(self, websocket: Any, topic: str = "dashboard") -> None:
        async with self._lock:
            self._connections[topic].discard(websocket)

    def count(self, topic: str | None = None) -> int:
        if topic:
            return len(self._connections.get(topic, ()))
        return sum(len(v) for v in self._connections.values())

    async def broadcast(self, event: str, data: dict[str, Any], topic: str = "dashboard") -> int:
        message = json.dumps(
            {
                "event": event,
                "topic": topic,
                "timestamp": datetime.now(UTC).isoformat(),
                "data": data,
            },
            ensure_ascii=False,
            default=str,
        )
        async with self._lock:
            targets = list(self._connections.get(topic, ()))
        delivered, dead = 0, []
        for ws in targets:
            try:
                await ws.send_text(message)
                delivered += 1
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections[topic].discard(ws)
        return delivered


manager = ConnectionManager()


# --------------------------------------------------------------------------
# Channel senders
# --------------------------------------------------------------------------
async def _send_email(recipient: str, subject: str, body: str) -> None:
    if settings.NOTIFICATIONS_DRY_RUN:
        logger.info("[DRY-RUN email] to=%s subject=%s", recipient, subject)
        return
    import smtplib

    message = EmailMessage()
    message["From"] = settings.MAIL_FROM
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    def _blocking_send() -> None:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
            if settings.SMTP_USER:
                smtp.starttls()
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(message)

    await asyncio.to_thread(_blocking_send)


async def _send_sms(recipient: str, body: str) -> None:
    if settings.NOTIFICATIONS_DRY_RUN:
        logger.info("[DRY-RUN sms] to=%s body=%s", recipient, body[:60])
        return
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            settings.SMS_PROVIDER_URL,
            json={"to": recipient, "text": body},
            headers={"Authorization": f"Bearer {settings.SMS_API_KEY}"},
        )
        response.raise_for_status()


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
async def dispatch(
    db: Session,
    *,
    channels: list[NotificationChannel],
    recipient: str,
    subject: str,
    body: str,
    alert_id: int | None = None,
    ws_event: str = "alert",
    ws_payload: dict[str, Any] | None = None,
    ws_topic: str = "dashboard",
) -> list[Notification]:
    """Persist one row per channel and attempt delivery immediately."""
    records: list[Notification] = []
    for channel in channels:
        note = Notification(
            alert_id=alert_id,
            channel=channel,
            recipient=recipient if channel != NotificationChannel.WEBSOCKET else ws_topic,
            subject=subject,
            body=body,
            status=NotificationStatus.QUEUED,
        )
        db.add(note)
        records.append(note)
    db.flush()

    for note in records:
        note.attempts += 1
        try:
            if note.channel == NotificationChannel.EMAIL:
                await _send_email(note.recipient, subject, body)
            elif note.channel == NotificationChannel.SMS:
                await _send_sms(note.recipient, body)
            else:
                await manager.broadcast(ws_event, ws_payload or {"subject": subject, "body": body}, ws_topic)
            note.status = NotificationStatus.SENT
            note.sent_at = datetime.now(UTC)
        except Exception as exc:
            note.status = NotificationStatus.FAILED
            note.error = str(exc)[:500]
            logger.warning("notification failed channel=%s error=%s", note.channel, exc)
    db.flush()
    return records


async def broadcast_event(event: str, data: dict[str, Any], topic: str = "dashboard") -> int:
    return await manager.broadcast(event, data, topic)
