from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import (
    AlertKind,
    AlertSeverity,
    AuditAction,
    IntegrationStatus,
    IntegrationSystem,
    NotificationChannel,
    NotificationStatus,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class AuditLog(Base):
    """Append-only, hash-chained audit trail (WORM semantics at app level)."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_actor_time", "actor_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)

    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_username: Mapped[str] = mapped_column(String(64), default="system", nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), default="system", nullable=False)

    action: Mapped[AuditAction] = mapped_column(String(32), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str] = mapped_column(String(500), default="", nullable=False)

    before_state: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    after_state: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    context: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON

    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_kind_ack", "kind", "acknowledged"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int | None] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[AlertKind] = mapped_column(String(40), nullable=False, index=True)
    severity: Mapped[AlertSeverity] = mapped_column(
        String(16), default=AlertSeverity.WARNING, nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    dedupe_key: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True, index=True)

    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    acknowledged_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    report = relationship("Report", back_populates="alerts")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True)
    channel: Mapped[NotificationChannel] = mapped_column(String(16), nullable=False, index=True)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(
        String(16), default=NotificationStatus.QUEUED, nullable=False, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IntegrationLog(Base):
    """Every outbound call to tax authority / bank / accounting, with retries."""

    __tablename__ = "integration_logs"
    __table_args__ = (Index("ix_integration_system_status", "system", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int | None] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), nullable=True, index=True
    )
    system: Mapped[IntegrationSystem] = mapped_column(String(32), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[IntegrationStatus] = mapped_column(
        String(16), default=IntegrationStatus.PENDING, nullable=False, index=True
    )

    request_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_reference: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)

    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[float | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    report = relationship("Report", back_populates="integrations")
