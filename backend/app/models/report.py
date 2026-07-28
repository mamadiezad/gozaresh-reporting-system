from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import (
    InstallmentStatus,
    ReportStatus,
    ReportType,
    StepStatus,
    WorkflowStage,
)
from app.models.types import Money

MONEY = Money  # exact 16-dp Decimal on every backend (see models/types.py)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Report(Base):
    """A financial report/request that flows through the approval workflow."""

    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_status_created", "status", "created_at"),
        Index("ix_reports_currency", "currency"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    report_type: Mapped[ReportType] = mapped_column(String(32), default=ReportType.LOAN, nullable=False)
    status: Mapped[ReportStatus] = mapped_column(String(32), default=ReportStatus.DRAFT, nullable=False, index=True)

    # --- Money -----------------------------------------------------------
    principal: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="IRR")
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="IRR")
    fx_rate: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    fx_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fx_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    amount_in_base: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)

    # --- Interest / schedule --------------------------------------------
    annual_rate: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0), nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    compounding_per_year: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    total_interest: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    total_payable: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    monthly_installment: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    effective_annual_rate: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    calc_duration_ms: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # --- Ownership / lifecycle -------------------------------------------
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    department: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    counterparty: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    creator = relationship("User", back_populates="reports", foreign_keys=[created_by_id])
    steps = relationship(
        "WorkflowStep",
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="WorkflowStep.order_index",
    )
    installments = relationship(
        "Installment",
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="Installment.number",
    )
    alerts = relationship("Alert", back_populates="report", cascade="all, delete-orphan")
    integrations = relationship("IntegrationLog", back_populates="report", cascade="all, delete-orphan")

    @property
    def current_stage(self) -> WorkflowStage | None:
        for step in self.steps:
            if step.status == StepStatus.PENDING:
                return step.stage
        return None


class WorkflowStep(Base):
    """One stage of the finance_manager -> inspector -> ceo approval chain."""

    __tablename__ = "workflow_steps"
    __table_args__ = (Index("ix_steps_report_order", "report_id", "order_index", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True)
    stage: Mapped[WorkflowStage] = mapped_column(String(32), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[StepStatus] = mapped_column(String(16), default=StepStatus.PENDING, nullable=False, index=True)

    approver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Digital signature over the canonical decision payload
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    signature_algorithm: Mapped[str | None] = mapped_column(String(32), nullable=True)
    signing_key_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    public_key_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    report = relationship("Report", back_populates="steps")
    approver = relationship("User", back_populates="approvals", foreign_keys=[approver_id])


class Installment(Base):
    __tablename__ = "installments"
    __table_args__ = (Index("ix_installments_due_status", "due_date", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    principal_component: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    interest_component: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    remaining_balance: Mapped[Decimal] = mapped_column(MONEY, nullable=False)

    status: Mapped[InstallmentStatus] = mapped_column(
        String(16), default=InstallmentStatus.SCHEDULED, nullable=False, index=True
    )
    paid_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bank_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)

    report = relationship("Report", back_populates="installments")


class ExchangeRate(Base):
    """Cached FX quote with provenance (which source, when, signature of raw)."""

    __tablename__ = "exchange_rates"
    __table_args__ = (Index("ix_fx_pair_time", "base", "quote", "fetched_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    base: Mapped[str] = mapped_column(String(3), nullable=False)
    quote: Mapped[str] = mapped_column(String(3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
