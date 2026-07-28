"""Domain enumerations shared by models, schemas and services."""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    VIEWER = "viewer"
    REQUESTER = "requester"
    FINANCE_MANAGER = "finance_manager"
    INSPECTOR = "inspector"
    CEO = "ceo"
    AUDITOR = "auditor"
    ADMIN = "admin"


class ReportStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PENDING_FINANCE = "pending_finance"
    PENDING_INSPECTOR = "pending_inspector"
    PENDING_CEO = "pending_ceo"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ReportType(StrEnum):
    LOAN = "loan"
    INSTALLMENT = "installment"
    INVESTMENT = "investment"
    EXPENSE = "expense"
    INVOICE = "invoice"
    SETTLEMENT = "settlement"


class WorkflowStage(StrEnum):
    FINANCE_MANAGER = "finance_manager"
    INSPECTOR = "inspector"
    CEO = "ceo"


class StepStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class InstallmentStatus(StrEnum):
    SCHEDULED = "scheduled"
    PAID = "paid"
    OVERDUE = "overdue"
    PARTIAL = "partial"
    WAIVED = "waived"


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertKind(StrEnum):
    OVERDUE_INSTALLMENT = "overdue_installment"
    OUT_OF_RANGE_TRANSACTION = "out_of_range_transaction"
    ANOMALY = "anomaly"
    WORKFLOW_STALLED = "workflow_stalled"
    INTEGRATION_FAILURE = "integration_failure"
    SECURITY = "security"


class NotificationChannel(StrEnum):
    EMAIL = "email"
    SMS = "sms"
    WEBSOCKET = "websocket"


class NotificationStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    SUPPRESSED = "suppressed"


class IntegrationSystem(StrEnum):
    MOADIAN = "moadian"  # Iranian tax authority
    BANK_GATEWAY = "bank_gateway"
    ACCOUNTING = "accounting"


class IntegrationStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


class AuditAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    READ = "read"
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    SUBMIT = "submit"
    APPROVE = "approve"
    REJECT = "reject"
    CALCULATE = "calculate"
    EXPORT = "export"
    INTEGRATION = "integration"
    ALERT = "alert"
    SECURITY = "security"
