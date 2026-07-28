"""Alerting engine: overdue installments, out-of-range amounts, anomalies."""

from __future__ import annotations

import json
import statistics
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.audit import Alert
from app.models.enums import (
    AlertKind,
    AlertSeverity,
    AuditAction,
    InstallmentStatus,
    NotificationChannel,
    ReportStatus,
    UserRole,
)
from app.models.report import Installment, Report
from app.models.user import User
from app.services import audit, notifier, workflow
from app.utils.money import ZERO, D, money_context, q

# Per-currency soft limits; anything above triggers a review alert.
TRANSACTION_LIMITS: dict[str, Decimal] = {
    "IRR": Decimal(50000000000),  # 50 billion rial
    "IRT": Decimal(5000000000),
    "USD": Decimal(100000),
    "EUR": Decimal(100000),
    "AED": Decimal(400000),
    "GBP": Decimal(80000),
}
DEFAULT_LIMIT = Decimal(100000)
MIN_SAMPLE_FOR_ANOMALY = 8


def _limit_for(currency: str) -> Decimal:
    return TRANSACTION_LIMITS.get(currency.upper(), DEFAULT_LIMIT)


def raise_alert(
    db: Session,
    *,
    kind: AlertKind,
    title: str,
    message: str,
    severity: AlertSeverity = AlertSeverity.WARNING,
    report_id: int | None = None,
    payload: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
) -> Alert | None:
    """Create an alert unless an identical one already exists (idempotent)."""
    if dedupe_key:
        existing = db.execute(select(Alert).where(Alert.dedupe_key == dedupe_key)).scalar_one_or_none()
        if existing:
            return None
    alert = Alert(
        report_id=report_id,
        kind=kind,
        severity=severity,
        title=title,
        message=message,
        payload=json.dumps(payload, ensure_ascii=False, default=str) if payload else None,
        dedupe_key=dedupe_key,
    )
    db.add(alert)
    db.flush()
    audit.record(
        db,
        action=AuditAction.ALERT,
        entity_type="alert",
        entity_id=alert.id,
        summary=title,
        after={"kind": str(kind), "severity": str(severity), "report_id": report_id},
    )
    return alert


async def publish(db: Session, alert: Alert, *, sms: bool = False) -> None:
    """Broadcast an alert live and email the responsible roles."""
    await notifier.broadcast_event(
        "alert.raised",
        {
            "id": alert.id,
            "kind": str(alert.kind),
            "severity": str(alert.severity),
            "title": alert.title,
            "message": alert.message,
            "report_id": alert.report_id,
            "created_at": alert.created_at.isoformat(),
        },
    )
    roles = [UserRole.FINANCE_MANAGER, UserRole.INSPECTOR]
    if alert.severity == AlertSeverity.CRITICAL:
        roles.append(UserRole.CEO)
    stakeholders = db.execute(select(User).where(User.role.in_(roles), User.is_active.is_(True))).scalars().all()
    channels = [NotificationChannel.EMAIL]
    if sms or alert.severity == AlertSeverity.CRITICAL:
        channels.append(NotificationChannel.SMS)
    for user in stakeholders:
        await notifier.dispatch(
            db,
            channels=channels,
            recipient=user.email,
            subject=f"[Gozaresh][{alert.severity}] {alert.title}",
            body=alert.message,
            alert_id=alert.id,
        )


# --------------------------------------------------------------------------
# Detectors
# --------------------------------------------------------------------------
def scan_overdue_installments(db: Session, *, today: date | None = None) -> list[Alert]:
    """Flag scheduled installments whose due date has passed."""
    today = today or date.today()
    cutoff = today - timedelta(days=settings.OVERDUE_GRACE_DAYS)
    rows = (
        db.execute(
            select(Installment).where(
                Installment.due_date < cutoff,
                Installment.status.in_([InstallmentStatus.SCHEDULED, InstallmentStatus.PARTIAL]),
            )
        )
        .scalars()
        .all()
    )

    created: list[Alert] = []
    for inst in rows:
        inst.status = InstallmentStatus.OVERDUE
        days_late = (today - inst.due_date).days
        severity = (
            AlertSeverity.CRITICAL if days_late > 30 else AlertSeverity.WARNING if days_late > 7 else AlertSeverity.INFO
        )
        report = db.get(Report, inst.report_id)
        alert = raise_alert(
            db,
            kind=AlertKind.OVERDUE_INSTALLMENT,
            severity=severity,
            title=f"Overdue installment #{inst.number} — {report.reference if report else inst.report_id}",
            message=(
                f"Installment #{inst.number} of {report.reference if report else ''} was due on "
                f"{inst.due_date.isoformat()} ({days_late} days late). Amount: {inst.amount} "
                f"{report.currency if report else ''}."
            ),
            report_id=inst.report_id,
            payload={
                "installment_id": inst.id,
                "number": inst.number,
                "due_date": inst.due_date.isoformat(),
                "days_late": days_late,
                "amount": str(inst.amount),
            },
            dedupe_key=f"overdue:{inst.id}",
        )
        if alert:
            created.append(alert)
    db.flush()
    return created


def check_transaction_range(db: Session, report: Report) -> Alert | None:
    """Detect amounts outside the permitted band for the currency."""
    limit = _limit_for(report.currency)
    amount = D(report.principal)
    if amount <= limit:
        return None
    with money_context():
        ratio = q(amount / limit) if limit else ZERO
    return raise_alert(
        db,
        kind=AlertKind.OUT_OF_RANGE_TRANSACTION,
        severity=AlertSeverity.CRITICAL if ratio > 2 else AlertSeverity.WARNING,
        title=f"Transaction above limit — {report.reference}",
        message=(
            f"Report {report.reference} has principal {report.principal} {report.currency}, "
            f"exceeding the {limit} {report.currency} threshold ({ratio}x)."
        ),
        report_id=report.id,
        payload={
            "principal": str(report.principal),
            "currency": report.currency,
            "limit": str(limit),
            "ratio": str(ratio),
        },
        dedupe_key=f"range:{report.id}",
    )


def detect_anomalies(db: Session, *, lookback_days: int = 180) -> list[Alert]:
    """Statistical outlier detection (modified z-score, robust to outliers)."""
    since = datetime.now(UTC) - timedelta(days=lookback_days)
    reports = db.execute(select(Report).where(Report.created_at >= since)).scalars().all()

    by_currency: dict[str, list[Report]] = {}
    for report in reports:
        by_currency.setdefault(report.currency, []).append(report)

    created: list[Alert] = []
    for currency, group in by_currency.items():
        if len(group) < MIN_SAMPLE_FOR_ANOMALY:
            continue
        amounts = [float(r.principal) for r in group]
        median = statistics.median(amounts)
        deviations = [abs(a - median) for a in amounts]
        mad = statistics.median(deviations)
        scale = mad * 1.4826 if mad > 0 else (statistics.pstdev(amounts) or 1.0)

        for report, amount in zip(group, amounts, strict=True):
            score = abs(amount - median) / scale
            if score < settings.ANOMALY_ZSCORE_THRESHOLD:
                continue
            alert = raise_alert(
                db,
                kind=AlertKind.ANOMALY,
                severity=AlertSeverity.WARNING,
                title=f"Statistical anomaly — {report.reference}",
                message=(
                    f"Report {report.reference} amount {report.principal} {currency} deviates "
                    f"{score:.2f}σ from the {currency} median ({median:,.2f})."
                ),
                report_id=report.id,
                payload={
                    "z_score": round(score, 4),
                    "median": median,
                    "currency": currency,
                },
                dedupe_key=f"anomaly:{report.id}",
            )
            if alert:
                created.append(alert)
    return created


def detect_stalled_workflows(db: Session) -> list[Alert]:
    created: list[Alert] = []
    for step in workflow.stalled_steps(db):
        report = db.get(Report, step.report_id)
        if report is None or report.status in {
            ReportStatus.APPROVED,
            ReportStatus.REJECTED,
            ReportStatus.CANCELLED,
        }:
            continue
        alert = raise_alert(
            db,
            kind=AlertKind.WORKFLOW_STALLED,
            severity=AlertSeverity.WARNING,
            title=f"Approval overdue at {step.stage} — {report.reference}",
            message=f"Stage '{step.stage}' of {report.reference} passed its SLA ({step.due_at:%Y-%m-%d %H:%M} UTC).",
            report_id=report.id,
            payload={
                "stage": str(step.stage),
                "due_at": step.due_at.isoformat() if step.due_at else None,
            },
            dedupe_key=f"stalled:{step.id}",
        )
        if alert:
            created.append(alert)
    return created


async def run_full_scan(db: Session) -> dict[str, int]:
    """Executed by the background scheduler and the manual /alerts/scan route."""
    overdue = scan_overdue_installments(db)
    anomalies = detect_anomalies(db)
    stalled = detect_stalled_workflows(db)
    for alert in [*overdue, *anomalies, *stalled]:
        await publish(db, alert)
    db.flush()
    return {
        "overdue_installments": len(overdue),
        "anomalies": len(anomalies),
        "stalled_workflows": len(stalled),
        "total": len(overdue) + len(anomalies) + len(stalled),
    }


def summary(db: Session) -> dict[str, Any]:
    total = db.execute(select(func.count(Alert.id))).scalar_one()
    unacked = db.execute(select(func.count(Alert.id)).where(Alert.acknowledged.is_(False))).scalar_one()
    by_severity = dict(db.execute(select(Alert.severity, func.count(Alert.id)).group_by(Alert.severity)).all())
    by_kind = dict(db.execute(select(Alert.kind, func.count(Alert.id)).group_by(Alert.kind)).all())
    return {
        "total": total,
        "unacknowledged": unacked,
        "by_severity": {str(k): v for k, v in by_severity.items()},
        "by_kind": {str(k): v for k, v in by_kind.items()},
    }
