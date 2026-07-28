"""Real-time, multi-currency calculation endpoints (feature #1)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import AuditContext, CurrentUser, DbSession
from app.core.config import settings
from app.models.enums import AuditAction
from app.schemas import CalculationRequest, CalculationResponse, ConvertRequest, RateOut
from app.services import audit, fx
from app.services.calculator import CalculationError, calculate

router = APIRouter(prefix="/calculations", tags=["calculations"])


@router.post("/preview", response_model=CalculationResponse)
async def preview(
    payload: CalculationRequest,
    db: DbSession,
    user: CurrentUser,
    ctx: AuditContext,
    response: Response,
):
    """Stateless calculation preview — no report is persisted.

    Returns the wall-clock duration and whether it met the 50 ms SLA.
    """
    fx_rate = None
    fx_source = None
    if payload.convert_to and payload.convert_to != payload.currency:
        try:
            quote = await fx.get_rate(payload.currency, payload.convert_to, db)
        except fx.FxError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        fx_rate, fx_source = quote.rate, quote.source

    try:
        result = calculate(
            principal=payload.principal,
            annual_rate_percent=payload.annual_rate_percent,
            term_months=payload.term_months,
            compounding_per_year=payload.compounding_per_year,
            currency=payload.currency,
            start_date=payload.start_date,
            frequency=payload.frequency,
            fx_rate=fx_rate,
            base_currency=payload.convert_to,
            fx_source=fx_source,
            with_schedule=payload.with_schedule,
        )
    except CalculationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    response.headers["X-Calc-Duration-Ms"] = f"{result.duration_ms:.4f}"
    response.headers["X-Calc-SLA-Met"] = str(result.within_sla).lower()

    audit.record(
        db,
        action=AuditAction.CALCULATE,
        entity_type="calculation",
        summary=f"Preview {payload.principal} {payload.currency} @ {payload.annual_rate_percent}% / {payload.term_months}m",
        actor_id=user.id,
        actor_username=user.username,
        actor_role=str(user.role),
        context={
            "duration_ms": round(result.duration_ms, 4),
            "within_sla": result.within_sla,
        },
        **ctx,
    )
    return result.as_dict(include_schedule=payload.with_schedule)


@router.get("/rates/{base}/{quote}", response_model=RateOut)
async def get_rate(base: str, quote: str, db: DbSession, user: CurrentUser):
    try:
        result = await fx.get_rate(base, quote, db)
    except fx.FxError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return result.as_dict()


@router.get("/rates/{base}")
async def rate_table(base: str, db: DbSession, user: CurrentUser):
    return {
        "base": base.upper(),
        "rates": await fx.rate_table(base, db),
        "supported": list(fx.SUPPORTED_CURRENCIES),
        "offline_mode": settings.FX_OFFLINE_MODE,
    }


@router.post("/convert")
async def convert(payload: ConvertRequest, db: DbSession, user: CurrentUser):
    try:
        amount, quote = await fx.convert(payload.amount, payload.base, payload.quote, db)
    except fx.FxError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return {
        "input_amount": str(payload.amount),
        "converted_amount": str(amount),
        **quote.as_dict(),
    }


@router.get("/benchmark")
async def benchmark(
    user: CurrentUser,
    iterations: int = Query(default=100, ge=1, le=2000),
    term_months: int = Query(default=60, ge=1, le=600),
):
    """Measure the calculation engine against the 50 ms SLA."""
    durations: list[float] = []
    for _ in range(iterations):
        result = calculate(
            principal="1250000000",
            annual_rate_percent="23.5",
            term_months=term_months,
            currency="IRR",
        )
        durations.append(result.duration_ms)

    durations.sort()

    def percentile(p: float) -> float:
        idx = min(len(durations) - 1, int(len(durations) * p))
        return round(durations[idx], 4)

    return {
        "iterations": iterations,
        "term_months": term_months,
        "sla_ms": settings.CALC_SLA_MS,
        "min_ms": round(durations[0], 4),
        "p50_ms": percentile(0.50),
        "p95_ms": percentile(0.95),
        "p99_ms": percentile(0.99),
        "max_ms": round(durations[-1], 4),
        "avg_ms": round(sum(durations) / len(durations), 4),
        "sla_met_ratio": round(sum(1 for d in durations if d <= settings.CALC_SLA_MS) / len(durations), 4),
    }
