"""Gozaresh — Enterprise Reporting Platform.

Application factory: middleware stack, routers, background scheduler.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1 import api_router
from app.core.config import settings
from app.core.database import SessionLocal, init_db
from app.services import alerts as alerts_service

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(name)s :: %(message)s",
)
logger = logging.getLogger("gozaresh")


async def _alert_scheduler() -> None:
    """Periodic detector sweep: overdue, anomalies, stalled approvals."""
    while True:
        try:
            await asyncio.sleep(settings.ALERT_SCAN_INTERVAL_SECONDS)
            with SessionLocal() as db:
                result = await alerts_service.run_full_scan(db)
                db.commit()
            if result["total"]:
                logger.info("alert scan raised %s new alerts", result["total"])
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("alert scheduler iteration failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("database ready (%s)", settings.DATABASE_URL.split("://")[0])

    task: asyncio.Task | None = None
    if settings.ENABLE_BACKGROUND_SCHEDULER and settings.ENV != "test":
        task = asyncio.create_task(_alert_scheduler())
        logger.info("alert scheduler started (every %ss)", settings.ALERT_SCAN_INTERVAL_SECONDS)

    yield

    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    logger.info("shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description=(
        "Multi-currency financial reporting with Decimal precision, a three-stage signed "
        "approval workflow, real-time dashboards, tax/bank integrations and a hash-chained audit trail."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# --------------------------------------------------------------------------
# Middleware (order matters: last added runs first)
# --------------------------------------------------------------------------
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Request-ID",
        "X-Process-Time-Ms",
        "X-Calc-Duration-Ms",
        "X-Calc-SLA-Met",
    ],
)
if settings.is_prod:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*.gozaresh.local", "localhost"])


@app.middleware("http")
async def security_and_tracing(request: Request, call_next):
    """Correlation IDs, timing headers and defence-in-depth response headers."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request.state.request_id = request_id
    started = time.perf_counter()

    response = await call_next(request)

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = f"{(time.perf_counter() - started) * 1000:.3f}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
    if settings.is_prod:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    return response


# --------------------------------------------------------------------------
# Error handling — never leak internals
# --------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Validation failed",
            "errors": [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()],
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    logger.exception("unhandled error request_id=%s", request_id)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error" if settings.is_prod else f"{type(exc).__name__}: {exc}",
            "request_id": request_id,
        },
    )


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/", tags=["meta"])
async def root():
    return {
        "name": settings.APP_NAME,
        "version": "1.0.0",
        "environment": settings.ENV,
        "docs": "/docs",
        "api": settings.API_V1_PREFIX,
        "features": [
            "Multi-currency Decimal calculations (16 dp) under a 50 ms SLA",
            "Three-stage signed approval workflow",
            "Real-time dashboard, alerts and WebSocket notifications",
            "Tax authority, bank gateway and accounting integrations",
            "Layered security with a hash-chained audit trail",
        ],
    }


@app.get("/health", tags=["meta"])
async def health():
    from sqlalchemy import text

    checks: dict[str, str] = {}
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    from app.services.notifier import manager

    checks["websocket_connections"] = str(manager.count())
    checks["fx_mode"] = "offline" if settings.FX_OFFLINE_MODE else "live"
    checks["integrations"] = "sandbox" if settings.INTEGRATIONS_SANDBOX else "live"

    healthy = all(not v.startswith("error") for v in checks.values())
    return JSONResponse(
        status_code=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "healthy" if healthy else "degraded", "checks": checks},
    )
