"""API v1 router assembly."""

from fastapi import APIRouter

from app.api.v1 import (
    alerts,
    audit,
    auth,
    calculations,
    dashboard,
    integrations,
    reports,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(calculations.router)
api_router.include_router(reports.router)
api_router.include_router(dashboard.router)
api_router.include_router(alerts.router)
api_router.include_router(audit.router)
api_router.include_router(integrations.router)

__all__ = ["api_router"]
