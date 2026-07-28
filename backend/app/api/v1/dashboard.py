"""Dashboard aggregates + live WebSocket channel (feature #3)."""

from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.api.deps import CurrentUser, DbSession
from app.core.database import SessionLocal
from app.core.security import decode_token
from app.services import dashboard as dashboard_service
from app.services.notifier import manager

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/overview")
async def overview(db: DbSession, user: CurrentUser):
    return dashboard_service.overview(db)


@router.get("/dashboard/kpis")
async def kpis(db: DbSession, user: CurrentUser):
    return dashboard_service.kpis(db)


@router.get("/dashboard/charts/status")
async def chart_status(db: DbSession, user: CurrentUser):
    return dashboard_service.status_breakdown(db)


@router.get("/dashboard/charts/currency")
async def chart_currency(db: DbSession, user: CurrentUser):
    return dashboard_service.currency_exposure(db)


@router.get("/dashboard/charts/trend")
async def chart_trend(db: DbSession, user: CurrentUser, months: int = Query(default=12, ge=1, le=36)):
    return dashboard_service.monthly_trend(db, months)


@router.get("/dashboard/charts/throughput")
async def chart_throughput(db: DbSession, user: CurrentUser):
    return dashboard_service.workflow_throughput(db)


@router.get("/dashboard/upcoming")
async def upcoming(db: DbSession, user: CurrentUser, days: int = Query(default=30, ge=1, le=365)):
    return dashboard_service.upcoming_installments(db, days)


@router.get("/dashboard/integrations")
async def integrations_health(db: DbSession, user: CurrentUser):
    return dashboard_service.integration_health(db)


# --------------------------------------------------------------------------
# WebSocket: live push of alerts, workflow transitions and payments
# --------------------------------------------------------------------------
@router.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket, token: str = Query(default="")):
    """Authenticated live channel. Connect with ?token=<access_token>."""
    try:
        claims = decode_token(token, expected_type="access")
    except ValueError:
        await websocket.close(code=4401, reason="Invalid or missing access token")
        return

    await manager.connect(websocket, "dashboard")
    try:
        with SessionLocal() as db:
            await websocket.send_json(
                {
                    "event": "snapshot",
                    "topic": "dashboard",
                    "data": {
                        "user": claims.get("username"),
                        "kpis": dashboard_service.kpis(db),
                    },
                }
            )
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json({"event": "pong", "topic": "dashboard", "data": {}})
            elif message == "refresh":
                with SessionLocal() as db:
                    await websocket.send_json(
                        {
                            "event": "snapshot",
                            "topic": "dashboard",
                            "data": {"kpis": dashboard_service.kpis(db)},
                        }
                    )
    except WebSocketDisconnect:
        await manager.disconnect(websocket, "dashboard")
    except Exception:
        await manager.disconnect(websocket, "dashboard")


@router.get("/ws/status")
async def ws_status(user: CurrentUser):
    return {
        "active_connections": manager.count(),
        "dashboard_connections": manager.count("dashboard"),
    }
