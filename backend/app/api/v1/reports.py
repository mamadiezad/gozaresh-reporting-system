"""Report CRUD plus the multi-stage approval workflow (features #1 and #2)."""

from __future__ import annotations

import math
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import AuditContext, CurrentUser, DbSession
from app.core.config import settings
from app.models.enums import AuditAction, ReportStatus, ReportType, UserRole
from app.models.report import Installment, Report
from app.schemas import (
    DecisionRequest,
    PaginatedReports,
    ReportCreate,
    ReportDetail,
    ReportOut,
    WorkflowStepOut,
)
from app.services import alerts as alerts_service
from app.services import audit, fx, notifier, workflow
from app.services.calculator import CalculationError, calculate

router = APIRouter(prefix="/reports", tags=["reports"])

READ_ALL_ROLES = {
    UserRole.ADMIN,
    UserRole.AUDITOR,
    UserRole.FINANCE_MANAGER,
    UserRole.INSPECTOR,
    UserRole.CEO,
}


def _visible(query, user):
    if str(user.role) in {str(r) for r in READ_ALL_ROLES}:
        return query
    return query.where(Report.created_by_id == user.id)


def _get_or_404(db, report_id: int) -> Report:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Report {report_id} not found")
    return report


def _assert_can_read(report: Report, user) -> None:
    if str(user.role) in {str(r) for r in READ_ALL_ROLES}:
        return
    if report.created_by_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You can only access your own reports")


# --------------------------------------------------------------------------
# Create / read
# --------------------------------------------------------------------------
@router.post("", response_model=ReportDetail, status_code=status.HTTP_201_CREATED)
async def create_report(payload: ReportCreate, db: DbSession, user: CurrentUser, ctx: AuditContext):
    """Create a draft report, calculate it, and pre-build the approval chain."""
    report = Report(
        reference=workflow.generate_reference(),
        title=payload.title,
        description=payload.description,
        report_type=payload.report_type,
        status=ReportStatus.DRAFT,
        principal=payload.principal,
        currency=payload.currency,
        base_currency=settings.BASE_CURRENCY,
        annual_rate=payload.annual_rate_percent / 100,
        term_months=payload.term_months,
        compounding_per_year=payload.compounding_per_year,
        start_date=payload.start_date,
        department=payload.department,
        counterparty=payload.counterparty,
        created_by_id=user.id,
    )
    db.add(report)
    db.flush()

    if payload.auto_calculate:
        await _run_calculation(db, report, payload)

    workflow.initialise_workflow(db, report)
    report.content_hash = workflow.report_content_hash(report)
    db.flush()

    range_alert = alerts_service.check_transaction_range(db, report)
    if range_alert:
        await alerts_service.publish(db, range_alert)

    audit.record(
        db,
        action=AuditAction.CREATE,
        entity_type="report",
        entity_id=report.id,
        summary=f"Report {report.reference} created ({report.principal} {report.currency})",
        actor_id=user.id,
        actor_username=user.username,
        actor_role=str(user.role),
        after={
            "reference": report.reference,
            "principal": str(report.principal),
            "currency": report.currency,
            "total_payable": str(report.total_payable),
            "content_hash": report.content_hash,
        },
        **ctx,
    )
    await notifier.broadcast_event(
        "report.created",
        {
            "report_id": report.id,
            "reference": report.reference,
            "status": str(report.status),
            "creator": user.username,
        },
    )
    db.refresh(report)
    return report


async def _run_calculation(db, report: Report, payload: ReportCreate) -> None:
    fx_rate = fx_source = None
    if report.currency != settings.BASE_CURRENCY:
        try:
            quote = await fx.get_rate(report.currency, settings.BASE_CURRENCY, db)
            fx_rate, fx_source = quote.rate, quote.source
            report.fx_fetched_at = quote.fetched_at
        except fx.FxError:
            fx_rate = fx_source = None

    try:
        result = calculate(
            principal=report.principal,
            annual_rate_percent=payload.annual_rate_percent,
            term_months=report.term_months,
            compounding_per_year=report.compounding_per_year,
            currency=report.currency,
            start_date=report.start_date,
            fx_rate=fx_rate,
            base_currency=settings.BASE_CURRENCY,
            fx_source=fx_source,
        )
    except CalculationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    report.total_interest = result.total_interest
    report.total_payable = result.total_payable
    report.monthly_installment = result.periodic_payment
    report.effective_annual_rate = result.effective_annual_rate
    report.calc_duration_ms = result.duration_ms
    report.fx_rate = result.fx_rate
    report.fx_source = result.fx_source
    report.amount_in_base = result.amount_in_base or result.total_payable

    for row in result.schedule:
        db.add(
            Installment(
                report_id=report.id,
                number=row.number,
                due_date=row.due_date,
                amount=row.amount,
                principal_component=row.principal_component,
                interest_component=row.interest_component,
                remaining_balance=row.remaining_balance,
            )
        )
    db.flush()


@router.get("", response_model=PaginatedReports)
async def list_reports(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    status_filter: ReportStatus | None = Query(default=None, alias="status"),
    report_type: ReportType | None = None,
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    search: str | None = Query(default=None, max_length=120),
):
    query = select(Report)
    count_query = select(func.count(Report.id))

    if status_filter:
        query = query.where(Report.status == status_filter)
        count_query = count_query.where(Report.status == status_filter)
    if report_type:
        query = query.where(Report.report_type == report_type)
        count_query = count_query.where(Report.report_type == report_type)
    if currency:
        query = query.where(Report.currency == currency.upper())
        count_query = count_query.where(Report.currency == currency.upper())
    if search:
        pattern = f"%{search}%"
        query = query.where(Report.title.ilike(pattern) | Report.reference.ilike(pattern))
        count_query = count_query.where(Report.title.ilike(pattern) | Report.reference.ilike(pattern))

    query, count_query = _visible(query, user), _visible(count_query, user)
    total = db.execute(count_query).scalar_one()
    items = (
        db.execute(query.order_by(Report.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
        .scalars()
        .all()
    )

    return PaginatedReports(
        items=[ReportOut.model_validate(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 0,
    )


@router.get("/inbox", response_model=list[ReportOut])
async def approval_inbox(db: DbSession, user: CurrentUser):
    """Reports currently waiting on *this* user's role."""
    stage_status = {
        UserRole.FINANCE_MANAGER: ReportStatus.PENDING_FINANCE,
        UserRole.INSPECTOR: ReportStatus.PENDING_INSPECTOR,
        UserRole.CEO: ReportStatus.PENDING_CEO,
    }
    if str(user.role) == UserRole.ADMIN:
        wanted = list(stage_status.values())
    else:
        target = stage_status.get(UserRole(str(user.role)))
        if target is None:
            return []
        wanted = [target]
    rows = (
        db.execute(select(Report).where(Report.status.in_(wanted)).order_by(Report.submitted_at.asc())).scalars().all()
    )
    return [ReportOut.model_validate(r) for r in rows]


@router.get("/{report_id}", response_model=ReportDetail)
async def get_report(report_id: int, db: DbSession, user: CurrentUser):
    report = _get_or_404(db, report_id)
    _assert_can_read(report, user)
    return report


# --------------------------------------------------------------------------
# Workflow (feature #2)
# --------------------------------------------------------------------------
@router.post("/{report_id}/submit", response_model=ReportDetail)
async def submit_report(report_id: int, db: DbSession, user: CurrentUser, ctx: AuditContext):
    report = _get_or_404(db, report_id)
    if report.created_by_id != user.id and str(user.role) != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only the creator can submit this report")
    try:
        await workflow.submit(db, report, user, **ctx)
    except workflow.WorkflowError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.refresh(report)
    return report


@router.post("/{report_id}/decision", response_model=WorkflowStepOut)
async def decide(
    report_id: int,
    payload: DecisionRequest,
    db: DbSession,
    user: CurrentUser,
    ctx: AuditContext,
):
    """Approve or reject the current stage; the decision is digitally signed."""
    report = _get_or_404(db, report_id)
    try:
        step = await workflow.act(
            db,
            report,
            user,
            workflow.Decision(payload.approved, payload.comment),
            **ctx,
        )
    except workflow.WorkflowError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return step


@router.get("/{report_id}/workflow")
async def workflow_state(report_id: int, db: DbSession, user: CurrentUser):
    report = _get_or_404(db, report_id)
    _assert_can_read(report, user)
    current = workflow.current_step(report)
    allowed, reason = workflow.can_act(report, user)
    return {
        "report_id": report.id,
        "reference": report.reference,
        "status": str(report.status),
        "current_stage": str(current.stage) if current else None,
        "you_can_act": allowed,
        "reason": reason,
        "stages": [
            {
                "stage": str(s.stage),
                "order": s.order_index,
                "status": str(s.status),
                "approver_id": s.approver_id,
                "comment": s.comment,
                "acted_at": s.acted_at.isoformat() if s.acted_at else None,
                "due_at": s.due_at.isoformat() if s.due_at else None,
                "signed": bool(s.signature),
                "key_fingerprint": s.public_key_fingerprint,
            }
            for s in sorted(report.steps, key=lambda x: x.order_index)
        ],
    }


@router.get("/{report_id}/signatures")
async def verify_signatures(report_id: int, db: DbSession, user: CurrentUser):
    """Cryptographically re-verify every approval signature (feature #5)."""
    report = _get_or_404(db, report_id)
    _assert_can_read(report, user)
    return workflow.verify_report_signatures(db, report)


@router.get("/{report_id}/installments")
async def list_installments(report_id: int, db: DbSession, user: CurrentUser):
    report = _get_or_404(db, report_id)
    _assert_can_read(report, user)
    return [
        {
            "id": i.id,
            "number": i.number,
            "due_date": i.due_date.isoformat(),
            "amount": str(i.amount),
            "principal_component": str(i.principal_component),
            "interest_component": str(i.interest_component),
            "remaining_balance": str(i.remaining_balance),
            "status": str(i.status),
            "paid_amount": str(i.paid_amount),
            "paid_at": i.paid_at.isoformat() if i.paid_at else None,
        }
        for i in sorted(report.installments, key=lambda x: x.number)
    ]


@router.post("/{report_id}/installments/{number}/pay")
async def pay_installment(
    report_id: int,
    number: int,
    db: DbSession,
    user: CurrentUser,
    ctx: AuditContext,
    bank_reference: str = "",
):
    report = _get_or_404(db, report_id)
    _assert_can_read(report, user)
    inst = next((i for i in report.installments if i.number == number), None)
    if inst is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Installment #{number} not found")

    from app.models.enums import InstallmentStatus

    inst.status = InstallmentStatus.PAID
    inst.paid_amount = inst.amount
    inst.paid_at = datetime.now(UTC)
    inst.bank_reference = bank_reference or None
    db.flush()

    audit.record(
        db,
        action=AuditAction.UPDATE,
        entity_type="installment",
        entity_id=inst.id,
        summary=f"Installment #{number} of {report.reference} marked paid",
        actor_id=user.id,
        actor_username=user.username,
        actor_role=str(user.role),
        after={
            "status": "paid",
            "amount": str(inst.amount),
            "bank_reference": bank_reference,
        },
        **ctx,
    )
    await notifier.broadcast_event(
        "installment.paid",
        {
            "report_id": report.id,
            "reference": report.reference,
            "number": number,
            "amount": str(inst.amount),
        },
    )
    return {"status": "paid", "installment": number, "amount": str(inst.amount)}
