"""Three-stage approval workflow: finance manager -> inspector -> CEO.

Guarantees
----------
* Stages are strictly ordered; a stage cannot be skipped or reordered.
* Each decision is signed with the approver's RSA key over a canonical payload
  that binds the report content hash, so post-hoc edits invalidate signatures.
* Every transition writes an audit entry and pushes a real-time event.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.signing import (
    canonical_json,
    ensure_keypair,
    sha256_hex,
    sign_payload,
    verify_payload,
)
from app.models.enums import (
    AuditAction,
    NotificationChannel,
    ReportStatus,
    StepStatus,
    UserRole,
    WorkflowStage,
)
from app.models.report import Report, WorkflowStep
from app.models.user import User
from app.services import audit, notifier
from app.utils.money import q

# Canonical stage order — the single source of truth for the chain.
STAGE_ORDER: tuple[WorkflowStage, ...] = (
    WorkflowStage.FINANCE_MANAGER,
    WorkflowStage.INSPECTOR,
    WorkflowStage.CEO,
)

STAGE_ROLE: dict[WorkflowStage, UserRole] = {
    WorkflowStage.FINANCE_MANAGER: UserRole.FINANCE_MANAGER,
    WorkflowStage.INSPECTOR: UserRole.INSPECTOR,
    WorkflowStage.CEO: UserRole.CEO,
}

STAGE_STATUS: dict[WorkflowStage, ReportStatus] = {
    WorkflowStage.FINANCE_MANAGER: ReportStatus.PENDING_FINANCE,
    WorkflowStage.INSPECTOR: ReportStatus.PENDING_INSPECTOR,
    WorkflowStage.CEO: ReportStatus.PENDING_CEO,
}

STAGE_SLA_HOURS: dict[WorkflowStage, int] = {
    WorkflowStage.FINANCE_MANAGER: 24,
    WorkflowStage.INSPECTOR: 48,
    WorkflowStage.CEO: 72,
}


class WorkflowError(RuntimeError):
    """Illegal workflow transition."""


@dataclass(slots=True)
class Decision:
    approved: bool
    comment: str = ""


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def generate_reference() -> str:
    return f"GZR-{datetime.now(UTC):%Y%m}-{secrets.token_hex(3).upper()}"


def _amount(value: Decimal | None) -> str | None:
    """Canonical decimal rendering for hashing.

    `Decimal("125")` and `Decimal("125.0000000000000000")` are numerically equal
    but stringify differently, and the DB round-trip normalises the scale. Both
    must hash identically, otherwise a signature made before the flush fails to
    verify after a reload.
    """
    return None if value is None else str(q(value))


def report_content_hash(report: Report) -> str:
    """Binds the financial substance of a report; signatures cover this."""
    return sha256_hex(
        canonical_json(
            {
                "reference": report.reference,
                "title": report.title,
                "report_type": str(report.report_type),
                "principal": _amount(report.principal),
                "currency": report.currency,
                "annual_rate": _amount(report.annual_rate),
                "term_months": report.term_months,
                "compounding_per_year": report.compounding_per_year,
                "total_payable": _amount(report.total_payable),
                "total_interest": _amount(report.total_interest),
                "amount_in_base": _amount(report.amount_in_base),
                "created_by_id": report.created_by_id,
            }
        )
    )


def signing_key_id(user: User) -> str:
    return user.signing_key_id or f"user-{user.id}"


def ensure_user_key(db: Session, user: User) -> str:
    key_id = signing_key_id(user)
    public_pem = ensure_keypair(key_id)
    if not user.signing_key_id:
        user.signing_key_id = key_id
        user.public_key_pem = public_pem
        db.flush()
    return key_id


def _iso_utc(moment: datetime | None) -> str | None:
    """Timezone-normalised timestamp so signatures survive a DB round-trip.

    SQLite (and some drivers) return naive datetimes; without normalisation the
    payload rebuilt at verification time would differ from the signed one.
    """
    if moment is None:
        return None
    if moment.tzinfo is not None:
        moment = moment.astimezone(UTC)
    return moment.replace(tzinfo=None).isoformat(timespec="microseconds")


def signature_payload(
    report: Report,
    step: WorkflowStep,
    user: User,
    decision: Decision,
    acted_at: datetime,
) -> dict[str, Any]:
    return {
        "report_reference": report.reference,
        "report_content_hash": report_content_hash(report),
        "stage": str(step.stage),
        "order_index": step.order_index,
        "decision": "approved" if decision.approved else "rejected",
        "comment": decision.comment,
        "approver_id": user.id,
        "approver_username": user.username,
        "approver_role": str(user.role),
        "acted_at": _iso_utc(acted_at),
    }


# --------------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------------
def initialise_workflow(db: Session, report: Report) -> list[WorkflowStep]:
    """Create the three pending steps in canonical order."""
    if report.steps:
        raise WorkflowError("Workflow already initialised for this report")
    now = datetime.now(UTC)
    steps = [
        WorkflowStep(
            report_id=report.id,
            stage=stage,
            order_index=index,
            status=StepStatus.PENDING,
            due_at=now + timedelta(hours=STAGE_SLA_HOURS[stage]),
        )
        for index, stage in enumerate(STAGE_ORDER)
    ]
    # Append through the relationship (not db.add_all) so the already-loaded
    # `report.steps` collection stays in sync; otherwise the guard above sees a
    # stale empty list and a second call would insert duplicate stages.
    report.steps.extend(steps)
    db.flush()
    return steps


async def submit(db: Session, report: Report, actor: User, **audit_ctx: Any) -> Report:
    """Move DRAFT -> PENDING_FINANCE and notify the first approver."""
    if report.status != ReportStatus.DRAFT:
        raise WorkflowError(f"Only draft reports can be submitted (current: {report.status})")
    if report.total_payable is None:
        raise WorkflowError("Report must be calculated before submission")

    if not report.steps:
        initialise_workflow(db, report)

    report.status = STAGE_STATUS[WorkflowStage.FINANCE_MANAGER]
    report.submitted_at = datetime.now(UTC)
    report.content_hash = report_content_hash(report)
    db.flush()

    audit.record(
        db,
        action=AuditAction.SUBMIT,
        entity_type="report",
        entity_id=report.id,
        summary=f"Report {report.reference} submitted for approval",
        actor_id=actor.id,
        actor_username=actor.username,
        actor_role=str(actor.role),
        after={"status": str(report.status), "content_hash": report.content_hash},
        **audit_ctx,
    )
    await _notify_stage(db, report, WorkflowStage.FINANCE_MANAGER)
    return report


def current_step(report: Report) -> WorkflowStep | None:
    for step in sorted(report.steps, key=lambda s: s.order_index):
        if step.status == StepStatus.PENDING:
            return step
    return None


def can_act(report: Report, user: User) -> tuple[bool, str]:
    step = current_step(report)
    if step is None:
        return False, "Workflow already completed"
    if report.status in {
        ReportStatus.DRAFT,
        ReportStatus.REJECTED,
        ReportStatus.CANCELLED,
        ReportStatus.APPROVED,
    }:
        return False, f"Report is {report.status}; no action possible"
    if user.role == UserRole.ADMIN:
        return True, "admin override"
    if str(user.role) != str(STAGE_ROLE[step.stage]):
        return (
            False,
            f"Stage {step.stage} requires role {STAGE_ROLE[step.stage]}, you are {user.role}",
        )
    return True, "ok"


async def act(db: Session, report: Report, actor: User, decision: Decision, **audit_ctx: Any) -> WorkflowStep:
    """Apply an approve/reject decision to the current stage, signed."""
    allowed, reason = can_act(report, actor)
    if not allowed:
        raise WorkflowError(reason)

    step = current_step(report)
    assert step is not None  # guarded by can_act
    acted_at = datetime.now(UTC)

    key_id = ensure_user_key(db, actor)
    payload = signature_payload(report, step, actor, decision, acted_at)
    signature = sign_payload(key_id, payload)

    step.status = StepStatus.APPROVED if decision.approved else StepStatus.REJECTED
    step.approver_id = actor.id
    step.comment = decision.comment
    step.acted_at = acted_at
    step.signature = signature["signature"]
    step.signature_algorithm = signature["algorithm"]
    step.signing_key_id = key_id
    step.payload_hash = signature["payload_hash"]
    step.public_key_fingerprint = signature["public_key_fingerprint"]

    if not decision.approved:
        report.status = ReportStatus.REJECTED
        report.completed_at = acted_at
        for later in report.steps:
            if later.status == StepStatus.PENDING:
                later.status = StepStatus.SKIPPED
    else:
        next_step = next(
            (s for s in sorted(report.steps, key=lambda x: x.order_index) if s.status == StepStatus.PENDING),
            None,
        )
        if next_step is None:
            report.status = ReportStatus.APPROVED
            report.completed_at = acted_at
        else:
            report.status = STAGE_STATUS[next_step.stage]
    db.flush()

    audit.record(
        db,
        action=AuditAction.APPROVE if decision.approved else AuditAction.REJECT,
        entity_type="workflow_step",
        entity_id=step.id,
        summary=f"{actor.username} {'approved' if decision.approved else 'rejected'} {report.reference} at {step.stage}",
        actor_id=actor.id,
        actor_username=actor.username,
        actor_role=str(actor.role),
        after={
            "stage": str(step.stage),
            "status": str(step.status),
            "report_status": str(report.status),
            "signature_hash": step.payload_hash,
            "key_fingerprint": step.public_key_fingerprint,
        },
        context={"comment": decision.comment},
        **audit_ctx,
    )

    await notifier.broadcast_event(
        "workflow.updated",
        {
            "report_id": report.id,
            "reference": report.reference,
            "stage": str(step.stage),
            "decision": str(step.status),
            "report_status": str(report.status),
            "actor": actor.username,
        },
    )

    if report.status == ReportStatus.APPROVED:
        await _notify_final(db, report, approved=True)
    elif report.status == ReportStatus.REJECTED:
        await _notify_final(db, report, approved=False)
    else:
        nxt = current_step(report)
        if nxt:
            await _notify_stage(db, report, nxt.stage)
    return step


def verify_step_signature(db: Session, report: Report, step: WorkflowStep) -> dict[str, Any]:
    """Re-verify a stored signature against the *current* report content."""
    if not step.signature or not step.approver_id:
        return {
            "stage": str(step.stage),
            "signed": False,
            "valid": False,
            "reason": "no signature recorded",
        }

    approver = db.get(User, step.approver_id)
    if approver is None:
        return {
            "stage": str(step.stage),
            "signed": True,
            "valid": False,
            "reason": "approver no longer exists",
        }

    decision = Decision(approved=step.status == StepStatus.APPROVED, comment=step.comment)
    payload = signature_payload(report, step, approver, decision, step.acted_at)
    valid = verify_payload(step.signing_key_id or signing_key_id(approver), payload, step.signature)
    return {
        "stage": str(step.stage),
        "signed": True,
        "valid": valid,
        "approver": approver.username,
        "acted_at": step.acted_at.isoformat() if step.acted_at else None,
        "key_fingerprint": step.public_key_fingerprint,
        "reason": None if valid else "signature does not match current report content (possible tampering)",
    }


def verify_report_signatures(db: Session, report: Report) -> dict[str, Any]:
    results = [verify_step_signature(db, report, s) for s in sorted(report.steps, key=lambda x: x.order_index)]
    signed = [r for r in results if r["signed"]]
    return {
        "report_reference": report.reference,
        "content_hash": report_content_hash(report),
        "stored_content_hash": report.content_hash,
        "content_unchanged": report.content_hash == report_content_hash(report) if report.content_hash else None,
        "all_valid": all(r["valid"] for r in signed) if signed else None,
        "steps": results,
    }


def stalled_steps(db: Session, *, now: datetime | None = None) -> list[WorkflowStep]:
    now = now or datetime.now(UTC)
    stmt = select(WorkflowStep).where(WorkflowStep.status == StepStatus.PENDING, WorkflowStep.due_at.is_not(None))
    return [s for s in db.execute(stmt).scalars().all() if s.due_at and s.due_at.replace(tzinfo=UTC) < now]


# --------------------------------------------------------------------------
# Notifications
# --------------------------------------------------------------------------
async def _recipients_for_role(db: Session, role: UserRole) -> list[User]:
    return list(db.execute(select(User).where(User.role == role, User.is_active.is_(True))).scalars().all())


async def _notify_stage(db: Session, report: Report, stage: WorkflowStage) -> None:
    role = STAGE_ROLE[stage]
    subject = f"[Gozaresh] Approval required — {report.reference}"
    body = (
        f"Report {report.reference} ({report.title}) awaits your approval at stage '{stage}'.\n"
        f"Amount: {report.principal} {report.currency} | Total payable: {report.total_payable}"
    )
    for user in await _recipients_for_role(db, role):
        await notifier.dispatch(
            db,
            channels=[NotificationChannel.EMAIL, NotificationChannel.WEBSOCKET],
            recipient=user.email,
            subject=subject,
            body=body,
            ws_event="workflow.pending",
            ws_payload={
                "report_id": report.id,
                "reference": report.reference,
                "stage": str(stage),
                "assignee_role": str(role),
                "status": str(report.status),
            },
        )


async def _notify_final(db: Session, report: Report, *, approved: bool) -> None:
    creator = db.get(User, report.created_by_id)
    verdict = "APPROVED" if approved else "REJECTED"
    subject = f"[Gozaresh] {report.reference} {verdict}"
    body = f"Your report {report.reference} ({report.title}) has been {verdict.lower()}."
    channels = [NotificationChannel.EMAIL, NotificationChannel.WEBSOCKET]
    if creator and creator.phone_encrypted:
        channels.append(NotificationChannel.SMS)
    await notifier.dispatch(
        db,
        channels=channels,
        recipient=creator.email if creator else "unknown@gozaresh-demo.com",
        subject=subject,
        body=body,
        ws_event="workflow.completed",
        ws_payload={
            "report_id": report.id,
            "reference": report.reference,
            "status": str(report.status),
        },
    )
