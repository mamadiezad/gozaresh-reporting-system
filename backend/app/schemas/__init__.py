"""Pydantic v2 request/response models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import (
    AlertKind,
    AlertSeverity,
    InstallmentStatus,
    ReportStatus,
    ReportType,
    StepStatus,
    UserRole,
    WorkflowStage,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, ser_json_timedelta="iso8601")


# --------------------------------------------------------------------------
# Auth & users
# --------------------------------------------------------------------------
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(default="", max_length=160)
    role: UserRole = UserRole.REQUESTER
    phone: str | None = Field(default=None, max_length=20)


class UserOut(ORMModel):
    id: int
    username: str
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    mfa_enabled: bool
    created_at: datetime
    last_login_at: datetime | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in_minutes: int
    user: UserOut


class RefreshRequest(BaseModel):
    refresh_token: str


# --------------------------------------------------------------------------
# Calculations
# --------------------------------------------------------------------------
class CalculationRequest(BaseModel):
    principal: Decimal = Field(gt=0, description="Principal amount in the source currency")
    annual_rate_percent: Decimal = Field(ge=0, le=200, description="Nominal annual rate, e.g. 23.5")
    term_months: int = Field(ge=0, le=600)
    compounding_per_year: int = Field(default=12, ge=1, le=365)
    currency: str = Field(default="IRR", min_length=3, max_length=3)
    convert_to: str | None = Field(default=None, min_length=3, max_length=3)
    start_date: date | None = None
    frequency: Literal["monthly", "quarterly", "semiannual", "annual"] = "monthly"
    with_schedule: bool = True

    @field_validator("currency", "convert_to")
    @classmethod
    def _upper(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class InstallmentOut(ORMModel):
    number: int
    due_date: date
    amount: Decimal
    principal_component: Decimal
    interest_component: Decimal
    remaining_balance: Decimal
    status: InstallmentStatus = InstallmentStatus.SCHEDULED


class CalculationResponse(BaseModel):
    principal: str
    currency: str
    annual_rate: str
    term_months: int
    compounding_per_year: int
    total_interest: str
    total_payable: str
    periodic_payment: str
    effective_annual_rate: str
    display_total: str
    fx_rate: str | None = None
    base_currency: str | None = None
    amount_in_base: str | None = None
    fx_source: str | None = None
    duration_ms: float
    within_sla: bool
    sla_ms: float
    schedule: list[dict[str, Any]] = Field(default_factory=list)


# --------------------------------------------------------------------------
# FX
# --------------------------------------------------------------------------
class RateOut(BaseModel):
    base: str
    quote: str
    rate: str
    source: str
    fetched_at: datetime
    is_stale: bool
    latency_ms: float


class ConvertRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    base: str = Field(min_length=3, max_length=3)
    quote: str = Field(min_length=3, max_length=3)


# --------------------------------------------------------------------------
# Reports & workflow
# --------------------------------------------------------------------------
class ReportCreate(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    description: str = Field(default="", max_length=4000)
    report_type: ReportType = ReportType.LOAN
    principal: Decimal = Field(gt=0)
    currency: str = Field(default="IRR", min_length=3, max_length=3)
    annual_rate_percent: Decimal = Field(default=Decimal(0), ge=0, le=200)
    term_months: int = Field(default=12, ge=0, le=600)
    compounding_per_year: int = Field(default=12, ge=1, le=365)
    start_date: date | None = None
    department: str = Field(default="", max_length=120)
    counterparty: str = Field(default="", max_length=200)
    auto_calculate: bool = True

    @field_validator("currency")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class WorkflowStepOut(ORMModel):
    id: int
    stage: WorkflowStage
    order_index: int
    status: StepStatus
    approver_id: int | None
    comment: str
    acted_at: datetime | None
    due_at: datetime | None
    signature_algorithm: str | None
    public_key_fingerprint: str | None


class ReportOut(ORMModel):
    id: int
    reference: str
    title: str
    description: str
    report_type: ReportType
    status: ReportStatus
    principal: Decimal
    currency: str
    base_currency: str
    fx_rate: Decimal | None
    fx_source: str | None
    amount_in_base: Decimal | None
    annual_rate: Decimal
    term_months: int
    total_interest: Decimal | None
    total_payable: Decimal | None
    monthly_installment: Decimal | None
    effective_annual_rate: Decimal | None
    calc_duration_ms: float | None
    department: str
    counterparty: str
    created_by_id: int
    content_hash: str | None
    created_at: datetime
    submitted_at: datetime | None
    completed_at: datetime | None


class ReportDetail(ReportOut):
    steps: list[WorkflowStepOut] = Field(default_factory=list)
    installments: list[InstallmentOut] = Field(default_factory=list)


class DecisionRequest(BaseModel):
    approved: bool
    comment: str = Field(default="", max_length=2000)


class PaginatedReports(BaseModel):
    items: list[ReportOut]
    total: int
    page: int
    page_size: int
    pages: int


# --------------------------------------------------------------------------
# Alerts
# --------------------------------------------------------------------------
class AlertOut(ORMModel):
    id: int
    report_id: int | None
    kind: AlertKind
    severity: AlertSeverity
    title: str
    message: str
    acknowledged: bool
    acknowledged_at: datetime | None
    created_at: datetime


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------
class AuditLogOut(ORMModel):
    id: int
    sequence: int
    actor_username: str
    actor_role: str
    action: str
    entity_type: str
    entity_id: str | None
    summary: str
    ip_address: str | None
    request_id: str | None
    previous_hash: str
    entry_hash: str
    created_at: datetime


class ChainVerification(BaseModel):
    valid: bool
    checked: int
    broken_at_sequence: int | None = None
    reason: str | None = None
    head_hash: str | None = None


# --------------------------------------------------------------------------
# Integrations
# --------------------------------------------------------------------------
class SettlementRequest(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0)
    iban: str = Field(default="", max_length=34)
    description: str = Field(default="", max_length=200)


class IntegrationLogOut(ORMModel):
    id: int
    report_id: int | None
    system: str
    operation: str
    status: str
    external_reference: str | None
    attempts: int
    duration_ms: float | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None
