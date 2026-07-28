"""Alert inbox, acknowledgement and on-demand scanning (feature #3)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import AuditContext, CurrentUser, DbSession
from app.models.audit import Alert
from app.models.enums import AlertKind, AlertSeverity, AuditAction
from app.schemas import AlertOut
from app.services import alerts as alerts_service
from app.services import audit

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    db: DbSession,
    user: CurrentUser,
    acknowledged: bool | None = None,
    severity: AlertSeverity | None = None,
    kind: AlertKind | None = None,
    limit: int = Query(default=50, ge=1, le=500),
):
    query = select(Alert)
    if acknowledged is not None:
        query = query.where(Alert.acknowledged.is_(acknowledged))
    if severity:
        query = query.where(Alert.severity == severity)
    if kind:
        query = query.where(Alert.kind == kind)
    return list(db.execute(query.order_by(Alert.created_at.desc()).limit(limit)).scalars().all())


@router.get("/summary")
async def summary(db: DbSession, user: CurrentUser):
    return alerts_service.summary(db)


@router.post("/scan")
async def scan(db: DbSession, user: CurrentUser, ctx: AuditContext):
    """Run every detector now: overdue installments, anomalies, stalled approvals."""
    result = await alerts_service.run_full_scan(db)
    audit.record(
        db,
        action=AuditAction.ALERT,
        entity_type="alert_scan",
        summary=f"Manual alert scan produced {result['total']} new alerts",
        actor_id=user.id,
        actor_username=user.username,
        actor_role=str(user.role),
        context=result,
        **ctx,
    )
    return result


@router.post("/{alert_id}/acknowledge", response_model=AlertOut)
async def acknowledge(alert_id: int, db: DbSession, user: CurrentUser, ctx: AuditContext):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Alert {alert_id} not found")
    if alert.acknowledged:
        return alert

    alert.acknowledged = True
    alert.acknowledged_by_id = user.id
    alert.acknowledged_at = datetime.now(UTC)
    db.flush()

    audit.record(
        db,
        action=AuditAction.UPDATE,
        entity_type="alert",
        entity_id=alert.id,
        summary=f"Alert '{alert.title}' acknowledged by {user.username}",
        actor_id=user.id,
        actor_username=user.username,
        actor_role=str(user.role),
        after={"acknowledged": True},
        **ctx,
    )
    return alert
