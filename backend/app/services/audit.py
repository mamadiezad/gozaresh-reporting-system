"""Append-only audit trail with cryptographic hash chaining.

Every entry stores H(previous_hash || canonical(entry)). Deleting or editing
any historical row breaks the chain, and `verify_chain()` reports the exact
sequence number where tampering occurred.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.signing import GENESIS_HASH, chain_hash
from app.models.audit import AuditLog
from app.models.enums import AuditAction

_REDACT_KEYS = {
    "password",
    "hashed_password",
    "new_password",
    "old_password",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "api_key",
    "national_id",
    "phone_encrypted",
    "national_id_encrypted",
    "authorization",
}


def _sanitise(payload: Any) -> Any:
    """Never let credentials or raw PII reach the audit store."""
    if isinstance(payload, dict):
        return {k: ("***REDACTED***" if k.lower() in _REDACT_KEYS else _sanitise(v)) for k, v in payload.items()}
    if isinstance(payload, (list, tuple)):
        return [_sanitise(v) for v in payload]
    return payload


def _dump(payload: Any | None) -> str | None:
    if payload is None:
        return None
    return json.dumps(_sanitise(payload), ensure_ascii=False, sort_keys=True, default=str)


def _iso(moment: datetime) -> str:
    """Canonical UTC timestamp for hashing.

    Some backends (SQLite) drop tzinfo on round-trip, so we normalise to a
    naive-UTC representation. Without this the recomputed hash would differ
    from the stored one purely because of driver behaviour.
    """
    if moment.tzinfo is not None:
        moment = moment.astimezone(UTC).replace(tzinfo=None)
    return moment.isoformat(timespec="microseconds")


def _tail(db: Session) -> AuditLog | None:
    return db.execute(select(AuditLog).order_by(AuditLog.sequence.desc()).limit(1)).scalar_one_or_none()


def record(
    db: Session,
    *,
    action: AuditAction | str,
    entity_type: str,
    entity_id: str | int | None = None,
    summary: str = "",
    actor_id: int | None = None,
    actor_username: str = "system",
    actor_role: str = "system",
    before: Any | None = None,
    after: Any | None = None,
    context: Any | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> AuditLog:
    """Append one immutable, hash-linked entry. Caller controls the commit."""
    previous = _tail(db)
    previous_hash = previous.entry_hash if previous else GENESIS_HASH
    sequence = (previous.sequence + 1) if previous else 1
    created_at = datetime.now(UTC)

    body = {
        "sequence": sequence,
        "action": str(action),
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id is not None else None,
        "summary": summary,
        "actor_id": actor_id,
        "actor_username": actor_username,
        "actor_role": actor_role,
        "before_state": _dump(before),
        "after_state": _dump(after),
        "context": _dump(context),
        "ip_address": ip_address,
        "request_id": request_id,
        "created_at": _iso(created_at),
    }
    entry = AuditLog(
        **{k: v for k, v in body.items() if k != "created_at"},
        created_at=created_at,
        user_agent=(user_agent or "")[:300] or None,
        previous_hash=previous_hash,
        entry_hash=chain_hash(previous_hash, body),
    )
    db.add(entry)
    db.flush()
    return entry


def verify_chain(db: Session, *, limit: int | None = None) -> dict[str, Any]:
    """Recompute the whole chain and report the first break, if any."""
    stmt = select(AuditLog).order_by(AuditLog.sequence.asc())
    if limit:
        stmt = stmt.limit(limit)
    rows = db.execute(stmt).scalars().all()

    previous_hash = GENESIS_HASH
    for row in rows:
        body = {
            "sequence": row.sequence,
            "action": str(row.action),
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "summary": row.summary,
            "actor_id": row.actor_id,
            "actor_username": row.actor_username,
            "actor_role": row.actor_role,
            "before_state": row.before_state,
            "after_state": row.after_state,
            "context": row.context,
            "ip_address": row.ip_address,
            "request_id": row.request_id,
            "created_at": _iso(row.created_at),
        }
        if row.previous_hash != previous_hash:
            return {
                "valid": False,
                "checked": len(rows),
                "broken_at_sequence": row.sequence,
                "reason": "previous_hash mismatch — an earlier entry was altered or removed",
            }
        expected = chain_hash(previous_hash, body)
        if expected != row.entry_hash:
            return {
                "valid": False,
                "checked": len(rows),
                "broken_at_sequence": row.sequence,
                "reason": "entry_hash mismatch — this entry's content was modified",
            }
        previous_hash = row.entry_hash

    return {
        "valid": True,
        "checked": len(rows),
        "head_hash": previous_hash,
        "broken_at_sequence": None,
    }


def stats(db: Session) -> dict[str, Any]:
    total = db.execute(select(func.count(AuditLog.id))).scalar_one()
    by_action = dict(db.execute(select(AuditLog.action, func.count(AuditLog.id)).group_by(AuditLog.action)).all())
    head = _tail(db)
    return {
        "total_entries": total,
        "by_action": {str(k): v for k, v in by_action.items()},
        "head_sequence": head.sequence if head else 0,
        "head_hash": head.entry_hash if head else GENESIS_HASH,
    }
