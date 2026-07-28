"""ORM models — importing this package registers every mapper."""

from app.models.audit import Alert, AuditLog, IntegrationLog, Notification
from app.models.enums import (
    AlertKind,
    AlertSeverity,
    AuditAction,
    InstallmentStatus,
    IntegrationStatus,
    IntegrationSystem,
    NotificationChannel,
    NotificationStatus,
    ReportStatus,
    ReportType,
    StepStatus,
    UserRole,
    WorkflowStage,
)
from app.models.report import ExchangeRate, Installment, Report, WorkflowStep
from app.models.user import ApiKey, User

__all__ = [
    "Alert",
    "AlertKind",
    "AlertSeverity",
    "ApiKey",
    "AuditAction",
    "AuditLog",
    "ExchangeRate",
    "Installment",
    "InstallmentStatus",
    "IntegrationLog",
    "IntegrationStatus",
    "IntegrationSystem",
    "Notification",
    "NotificationChannel",
    "NotificationStatus",
    "Report",
    "ReportStatus",
    "ReportType",
    "StepStatus",
    "User",
    "UserRole",
    "WorkflowStage",
    "WorkflowStep",
]
