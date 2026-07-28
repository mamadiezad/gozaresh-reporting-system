"""Tax authority, bank gateway and accounting endpoints (feature #4)."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Query, Response, status
from sqlalchemy import select

from app.api.deps import AuditContext, CurrentUser, DbSession
from app.core.config import settings
from app.integrations import (
    AccountingConnector,
    BankConnector,
    IntegrationError,
    MoadianConnector,
    build_voucher,
    parse_voucher_xml,
    validate_iban,
    voucher_to_xml,
)
from app.models.audit import IntegrationLog
from app.models.enums import IntegrationSystem, ReportStatus
from app.models.report import Report
from app.schemas import IntegrationLogOut, SettlementRequest

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _get_report(db, report_id: int) -> Report:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Report {report_id} not found")
    return report


def _require_approved(report: Report) -> None:
    if report.status != ReportStatus.APPROVED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"Report must be APPROVED before integration (current: {report.status})",
        )


# --------------------------------------------------------------------------
# Tax authority (سامانه مودیان)
# --------------------------------------------------------------------------
@router.post("/moadian/{report_id}/submit")
async def submit_to_moadian(report_id: int, db: DbSession, user: CurrentUser, ctx: AuditContext):
    report = _get_report(db, report_id)
    _require_approved(report)
    connector = MoadianConnector(db, sandbox=settings.INTEGRATIONS_SANDBOX)
    try:
        return await connector.submit_report(report)
    except IntegrationError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/moadian/{report_id}/preview")
async def preview_moadian_invoice(report_id: int, db: DbSession, user: CurrentUser):
    """Inspect the exact invoice envelope before it is transmitted."""
    return MoadianConnector.build_invoice(_get_report(db, report_id))


@router.post("/moadian/inquiry")
async def moadian_inquiry(db: DbSession, user: CurrentUser, uid: str = Body(embed=True)):
    connector = MoadianConnector(db, sandbox=settings.INTEGRATIONS_SANDBOX)
    try:
        _, response = await connector.execute("inquiry", {"uid": uid})
    except IntegrationError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return response


# --------------------------------------------------------------------------
# Bank gateway
# --------------------------------------------------------------------------
@router.post("/bank/{report_id}/settle")
async def request_settlement(
    report_id: int,
    payload: SettlementRequest,
    db: DbSession,
    user: CurrentUser,
    ctx: AuditContext,
):
    report = _get_report(db, report_id)
    _require_approved(report)
    if payload.iban and not validate_iban(payload.iban):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid IBAN checksum")

    connector = BankConnector(db, sandbox=settings.INTEGRATIONS_SANDBOX)
    try:
        return await connector.request_settlement(
            report_id=report.id,
            amount=payload.amount or report.total_payable or report.principal,
            currency=report.currency,
            iban=payload.iban,
            description=payload.description or report.title,
        )
    except IntegrationError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/bank/{report_id}/confirm")
async def confirm_settlement(
    report_id: int,
    db: DbSession,
    user: CurrentUser,
    tracking_id: str = Body(embed=True),
):
    report = _get_report(db, report_id)
    connector = BankConnector(db, sandbox=settings.INTEGRATIONS_SANDBOX)
    try:
        return await connector.confirm_settlement(report_id=report.id, tracking_id=tracking_id)
    except IntegrationError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/bank/validate-iban")
async def check_iban(user: CurrentUser, iban: str = Query(min_length=15, max_length=34)):
    return {"iban": iban.upper().replace(" ", ""), "valid": validate_iban(iban)}


# --------------------------------------------------------------------------
# Accounting / ERP (JSON + XML)
# --------------------------------------------------------------------------
@router.post("/accounting/{report_id}/push")
async def push_to_accounting(report_id: int, db: DbSession, user: CurrentUser, ctx: AuditContext):
    report = _get_report(db, report_id)
    _require_approved(report)
    connector = AccountingConnector(db, sandbox=settings.INTEGRATIONS_SANDBOX)
    try:
        return await connector.push_report(report)
    except IntegrationError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/accounting/{report_id}/voucher.json")
async def voucher_json(report_id: int, db: DbSession, user: CurrentUser):
    return build_voucher(_get_report(db, report_id))


@router.get("/accounting/{report_id}/voucher.xml")
async def voucher_xml(report_id: int, db: DbSession, user: CurrentUser):
    xml = voucher_to_xml(build_voucher(_get_report(db, report_id)))
    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="voucher-{report_id}.xml"'},
    )


@router.post("/accounting/import-xml")
async def import_voucher_xml(user: CurrentUser, xml_body: str = Body(media_type="application/xml")):
    """Inbound channel so partner ERPs can push standard XML documents to us."""
    try:
        return {"parsed": parse_voucher_xml(xml_body)}
    except Exception as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Malformed XML: {exc}") from exc


# --------------------------------------------------------------------------
# Observability
# --------------------------------------------------------------------------
@router.get("/logs", response_model=list[IntegrationLogOut])
async def integration_logs(
    db: DbSession,
    user: CurrentUser,
    system: IntegrationSystem | None = None,
    report_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=500),
):
    query = select(IntegrationLog)
    if system:
        query = query.where(IntegrationLog.system == system)
    if report_id:
        query = query.where(IntegrationLog.report_id == report_id)
    return list(db.execute(query.order_by(IntegrationLog.created_at.desc()).limit(limit)).scalars().all())
