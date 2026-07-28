"""Audit trail browsing, chain verification and export (feature #5)."""

from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select

from app.api.deps import AuditContext, CurrentUser, DbSession, require_permission
from app.models.audit import AuditLog
from app.models.enums import AuditAction
from app.schemas import AuditLogOut, ChainVerification
from app.services import audit as audit_service

router = APIRouter(
    prefix="/audit",
    tags=["audit"],
    dependencies=[Depends(require_permission("audit:read"))],
)


@router.get("/logs", response_model=list[AuditLogOut])
async def list_logs(
    db: DbSession,
    user: CurrentUser,
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: AuditAction | None = None,
    actor_username: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    query = select(AuditLog)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)
    if action:
        query = query.where(AuditLog.action == action)
    if actor_username:
        query = query.where(AuditLog.actor_username == actor_username)
    return list(db.execute(query.order_by(AuditLog.sequence.desc()).offset(offset).limit(limit)).scalars().all())


@router.get("/verify", response_model=ChainVerification)
async def verify_chain(db: DbSession, user: CurrentUser):
    """Recompute the hash chain end-to-end and report the first break."""
    return audit_service.verify_chain(db)


@router.get("/stats")
async def stats(db: DbSession, user: CurrentUser):
    return audit_service.stats(db)


@router.get("/trail/{entity_type}/{entity_id}", response_model=list[AuditLogOut])
async def entity_trail(entity_type: str, entity_id: str, db: DbSession, user: CurrentUser):
    """Full chronological history of one entity."""
    return list(
        db.execute(
            select(AuditLog)
            .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
            .order_by(AuditLog.sequence.asc())
        )
        .scalars()
        .all()
    )


@router.get("/export")
async def export_trail(
    db: DbSession,
    user: CurrentUser,
    ctx: AuditContext,
    fmt: str = Query(default="csv", pattern="^(csv|json)$"),
    limit: int = Query(default=5000, ge=1, le=50000),
):
    """Export the audit trail for external archival (WORM storage, SIEM)."""
    rows = list(db.execute(select(AuditLog).order_by(AuditLog.sequence.asc()).limit(limit)).scalars().all())
    columns = [
        "sequence",
        "created_at",
        "actor_username",
        "actor_role",
        "action",
        "entity_type",
        "entity_id",
        "summary",
        "ip_address",
        "request_id",
        "previous_hash",
        "entry_hash",
    ]

    audit_service.record(
        db,
        action=AuditAction.EXPORT,
        entity_type="audit_log",
        summary=f"{user.username} exported {len(rows)} audit entries as {fmt}",
        actor_id=user.id,
        actor_username=user.username,
        actor_role=str(user.role),
        **ctx,
    )

    if fmt == "json":
        payload = [
            {c: (getattr(r, c).isoformat() if c == "created_at" else getattr(r, c)) for c in columns} for r in rows
        ]
        return Response(
            content=json.dumps(
                {"entries": payload, "count": len(payload)},
                ensure_ascii=False,
                indent=2,
            ),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="audit-trail.json"'},
        )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for r in rows:
        writer.writerow([r.created_at.isoformat() if c == "created_at" else getattr(r, c) for c in columns])
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit-trail.csv"'},
    )
