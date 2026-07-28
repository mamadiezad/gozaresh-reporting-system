"""Aggregations powering the real-time dashboard and interactive charts."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit import Alert, IntegrationLog
from app.models.enums import (
    AlertSeverity,
    InstallmentStatus,
    IntegrationStatus,
    ReportStatus,
    StepStatus,
)
from app.models.report import Installment, Report, WorkflowStep
from app.services import alerts as alerts_service
from app.utils.money import ZERO, D, money_context, q

ACTIVE_STATUSES = (
    ReportStatus.SUBMITTED,
    ReportStatus.PENDING_FINANCE,
    ReportStatus.PENDING_INSPECTOR,
    ReportStatus.PENDING_CEO,
)


def _sum(db: Session, column, *where) -> Decimal:
    value = db.execute(select(func.sum(column)).where(*where)).scalar_one_or_none()
    return D(value) if value is not None else ZERO


def kpis(db: Session) -> dict[str, Any]:
    total_reports = db.execute(select(func.count(Report.id))).scalar_one()
    approved = db.execute(select(func.count(Report.id)).where(Report.status == ReportStatus.APPROVED)).scalar_one()
    rejected = db.execute(select(func.count(Report.id)).where(Report.status == ReportStatus.REJECTED)).scalar_one()
    pending = db.execute(select(func.count(Report.id)).where(Report.status.in_(ACTIVE_STATUSES))).scalar_one()

    total_value_base = _sum(db, Report.amount_in_base)
    approved_value_base = _sum(db, Report.amount_in_base, Report.status == ReportStatus.APPROVED)

    overdue_count = db.execute(
        select(func.count(Installment.id)).where(Installment.status == InstallmentStatus.OVERDUE)
    ).scalar_one()
    overdue_amount = _sum(db, Installment.amount, Installment.status == InstallmentStatus.OVERDUE)

    unacked_alerts = db.execute(select(func.count(Alert.id)).where(Alert.acknowledged.is_(False))).scalar_one()
    critical_alerts = db.execute(
        select(func.count(Alert.id)).where(Alert.severity == AlertSeverity.CRITICAL, Alert.acknowledged.is_(False))
    ).scalar_one()

    avg_calc_ms = db.execute(select(func.avg(Report.calc_duration_ms))).scalar_one_or_none()

    with money_context():
        approval_rate = q(D(approved) * 100 / D(total_reports)) if total_reports else ZERO

    return {
        "total_reports": total_reports,
        "approved": approved,
        "rejected": rejected,
        "pending": pending,
        "approval_rate_percent": str(approval_rate),
        "total_value_base": str(total_value_base),
        "approved_value_base": str(approved_value_base),
        "overdue_installments": overdue_count,
        "overdue_amount": str(overdue_amount),
        "unacknowledged_alerts": unacked_alerts,
        "critical_alerts": critical_alerts,
        "avg_calc_duration_ms": round(float(avg_calc_ms), 3) if avg_calc_ms is not None else None,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def status_breakdown(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(select(Report.status, func.count(Report.id)).group_by(Report.status)).all()
    return [{"status": str(status), "count": count} for status, count in rows]


def currency_exposure(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            Report.currency,
            func.count(Report.id),
            func.sum(Report.principal),
            func.sum(Report.amount_in_base),
        ).group_by(Report.currency)
    ).all()
    return [
        {
            "currency": currency,
            "count": count,
            "total_principal": str(D(principal or 0)),
            "total_in_base": str(D(in_base or 0)),
        }
        for currency, count, principal, in_base in rows
    ]


def monthly_trend(db: Session, months: int = 12) -> list[dict[str, Any]]:
    since = datetime.now(UTC) - timedelta(days=31 * months)
    reports = db.execute(select(Report).where(Report.created_at >= since)).scalars().all()

    buckets: dict[str, dict[str, Any]] = {}
    for report in reports:
        key = f"{report.created_at.year:04d}-{report.created_at.month:02d}"
        bucket = buckets.setdefault(key, {"month": key, "count": 0, "approved": 0, "value_base": ZERO})
        bucket["count"] += 1
        if report.status == ReportStatus.APPROVED:
            bucket["approved"] += 1
        if report.amount_in_base:
            bucket["value_base"] += D(report.amount_in_base)

    return [{**b, "value_base": str(b["value_base"])} for b in sorted(buckets.values(), key=lambda x: x["month"])]


def workflow_throughput(db: Session) -> list[dict[str, Any]]:
    """Average hours spent per approval stage — spot the bottleneck."""
    steps = (
        db.execute(select(WorkflowStep).where(WorkflowStep.status.in_([StepStatus.APPROVED, StepStatus.REJECTED])))
        .scalars()
        .all()
    )

    agg: dict[str, list[float]] = {}
    counts: dict[str, dict[str, int]] = {}
    for step in steps:
        stage = str(step.stage)
        counts.setdefault(stage, {"approved": 0, "rejected": 0})
        counts[stage]["approved" if step.status == StepStatus.APPROVED else "rejected"] += 1
        if step.acted_at and step.created_at:
            hours = (step.acted_at.replace(tzinfo=UTC) - step.created_at.replace(tzinfo=UTC)).total_seconds() / 3600
            agg.setdefault(stage, []).append(hours)

    return [
        {
            "stage": stage,
            "approved": data["approved"],
            "rejected": data["rejected"],
            "avg_hours": round(sum(agg.get(stage, [0])) / len(agg[stage]), 2) if agg.get(stage) else None,
        }
        for stage, data in counts.items()
    ]


def upcoming_installments(db: Session, days: int = 30, limit: int = 20) -> list[dict[str, Any]]:
    today = date.today()
    horizon = today + timedelta(days=days)
    rows = (
        db.execute(
            select(Installment)
            .where(
                Installment.due_date.between(today, horizon),
                Installment.status.in_([InstallmentStatus.SCHEDULED, InstallmentStatus.PARTIAL]),
            )
            .order_by(Installment.due_date.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )

    out = []
    for inst in rows:
        report = db.get(Report, inst.report_id)
        out.append(
            {
                "installment_id": inst.id,
                "report_id": inst.report_id,
                "reference": report.reference if report else None,
                "number": inst.number,
                "due_date": inst.due_date.isoformat(),
                "days_until": (inst.due_date - today).days,
                "amount": str(inst.amount),
                "currency": report.currency if report else None,
                "status": str(inst.status),
            }
        )
    return out


def integration_health(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        select(IntegrationLog.system, IntegrationLog.status, func.count(IntegrationLog.id)).group_by(
            IntegrationLog.system, IntegrationLog.status
        )
    ).all()
    health: dict[str, dict[str, Any]] = {}
    for system, status, count in rows:
        entry = health.setdefault(
            str(system),
            {"system": str(system), "success": 0, "failed": 0, "pending": 0},
        )
        if status == IntegrationStatus.SUCCESS:
            entry["success"] += count
        elif status == IntegrationStatus.FAILED:
            entry["failed"] += count
        else:
            entry["pending"] += count
    for entry in health.values():
        total = entry["success"] + entry["failed"] + entry["pending"]
        entry["success_rate"] = round(entry["success"] * 100 / total, 2) if total else None
    return list(health.values())


def overview(db: Session) -> dict[str, Any]:
    """Single round-trip payload for the dashboard's first paint."""
    return {
        "kpis": kpis(db),
        "status_breakdown": status_breakdown(db),
        "currency_exposure": currency_exposure(db),
        "monthly_trend": monthly_trend(db),
        "workflow_throughput": workflow_throughput(db),
        "upcoming_installments": upcoming_installments(db),
        "integration_health": integration_health(db),
        "alerts": alerts_service.summary(db),
    }
