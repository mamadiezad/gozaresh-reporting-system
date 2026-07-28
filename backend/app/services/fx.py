"""Multi-currency FX service.

Provider chain:
    1. Central bank feed (authoritative, primary)
    2. Public exchange API (fallback)
    3. Persisted last-known-good rate from the DB (marked stale)

An in-process TTL cache keeps the hot path far below the 50 ms SLA, and every
quote records its provenance so audits can reproduce any historical figure.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.report import ExchangeRate
from app.utils.money import D, money_context, q

# Deterministic offline fixtures (units of currency per 1 unit listed below).
# Used when FX_OFFLINE_MODE=true so CI never depends on the network.
OFFLINE_RATES_PER_USD: dict[str, str] = {
    "USD": "1",
    "IRR": "587500",
    "IRT": "58750",
    "EUR": "0.9210",
    "GBP": "0.7840",
    "AED": "3.6725",
    "TRY": "34.1500",
    "CNY": "7.1200",
    "JPY": "151.4000",
    "CHF": "0.8830",
    "CAD": "1.3620",
}

SUPPORTED_CURRENCIES = tuple(sorted(OFFLINE_RATES_PER_USD))


class FxError(RuntimeError):
    """No provider could supply a usable rate."""


@dataclass(slots=True)
class Quote:
    base: str
    quote: str
    rate: Decimal
    source: str
    fetched_at: datetime
    is_stale: bool = False
    latency_ms: float = 0.0

    def as_dict(self) -> dict:
        return {
            "base": self.base,
            "quote": self.quote,
            "rate": str(self.rate),
            "source": self.source,
            "fetched_at": self.fetched_at.isoformat(),
            "is_stale": self.is_stale,
            "latency_ms": round(self.latency_ms, 3),
        }


class _TTLCache:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._data: dict[tuple[str, str], tuple[float, Quote]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: tuple[str, str]) -> Quote | None:
        async with self._lock:
            hit = self._data.get(key)
            if not hit:
                return None
            stored_at, quote = hit
            if time.monotonic() - stored_at > self._ttl:
                self._data.pop(key, None)
                return None
            return quote

    async def set(self, key: tuple[str, str], quote: Quote) -> None:
        async with self._lock:
            self._data[key] = (time.monotonic(), quote)

    def clear(self) -> None:
        self._data.clear()


_cache = _TTLCache(settings.FX_CACHE_TTL_SECONDS)


def clear_cache() -> None:
    _cache.clear()


# --------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------
def _cross_rate(base: str, quote: str, per_usd: dict[str, Decimal]) -> Decimal:
    if base not in per_usd or quote not in per_usd:
        raise FxError(f"Unsupported currency pair {base}/{quote}")
    with money_context():
        return q(per_usd[quote] / per_usd[base])


async def _offline_provider(base: str, quote: str) -> Quote:
    table = {k: D(v) for k, v in OFFLINE_RATES_PER_USD.items()}
    return Quote(
        base,
        quote,
        _cross_rate(base, quote, table),
        "offline_fixture",
        datetime.now(UTC),
    )


async def _central_bank_provider(base: str, quote: str, client: httpx.AsyncClient) -> Quote:
    """Expected shape: {"rates": {"USD": "587500", ...}, "base": "IRR"}."""
    response = await client.get(settings.FX_CENTRAL_BANK_URL, params={"base": base, "symbols": quote})
    response.raise_for_status()
    body = response.json()
    rate = body.get("rates", {}).get(quote)
    if rate is None:
        raise FxError(f"Central bank feed has no quote for {quote}")
    return Quote(base, quote, q(D(rate)), "central_bank", datetime.now(UTC))


async def _exchange_api_provider(base: str, quote: str, client: httpx.AsyncClient) -> Quote:
    response = await client.get(settings.FX_EXCHANGE_API_URL, params={"base": base, "symbols": quote})
    response.raise_for_status()
    body = response.json()
    rate = body.get("rates", {}).get(quote)
    if rate is None:
        raise FxError(f"Exchange API has no quote for {quote}")
    return Quote(base, quote, q(D(rate)), "exchange_api", datetime.now(UTC))


def _last_known_good(db: Session, base: str, quote: str) -> Quote | None:
    stmt = (
        select(ExchangeRate)
        .where(ExchangeRate.base == base, ExchangeRate.quote == quote)
        .order_by(ExchangeRate.fetched_at.desc())
        .limit(1)
    )
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        return None
    return Quote(base, quote, row.rate, f"{row.source}(cached)", row.fetched_at, is_stale=True)


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
async def get_rate(base: str, quote: str, db: Session | None = None) -> Quote:
    """Resolve base->quote, trying cache, providers, then last-known-good."""
    base, quote = base.upper(), quote.upper()
    started = time.perf_counter()

    if base == quote:
        return Quote(base, quote, Decimal(1), "identity", datetime.now(UTC))

    cached = await _cache.get((base, quote))
    if cached:
        cached.latency_ms = (time.perf_counter() - started) * 1000
        return cached

    result: Quote | None = None
    errors: list[str] = []

    if settings.FX_OFFLINE_MODE:
        result = await _offline_provider(base, quote)
    else:
        timeout = httpx.Timeout(settings.FX_HTTP_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            for provider in (_central_bank_provider, _exchange_api_provider):
                try:
                    result = await provider(base, quote, client)
                    break
                except Exception as exc:
                    errors.append(f"{provider.__name__}: {exc}")

    if result is None and db is not None:
        result = _last_known_good(db, base, quote)

    if result is None:
        raise FxError(f"All FX providers failed for {base}/{quote}: {'; '.join(errors) or 'no data'}")

    result.latency_ms = (time.perf_counter() - started) * 1000
    await _cache.set((base, quote), result)

    if db is not None and not result.is_stale:
        db.add(
            ExchangeRate(
                base=base,
                quote=quote,
                rate=result.rate,
                source=result.source,
                fetched_at=result.fetched_at,
            )
        )
        db.flush()
    return result


async def convert(
    amount: Decimal | str | int, base: str, quote: str, db: Session | None = None
) -> tuple[Decimal, Quote]:
    q_ = await get_rate(base, quote, db)
    with money_context():
        return q(D(amount) * q_.rate), q_


async def rate_table(base: str, db: Session | None = None) -> dict[str, str]:
    """All supported quotes for one base — powers the dashboard FX widget."""
    base = base.upper()
    out: dict[str, str] = {}
    for code in SUPPORTED_CURRENCIES:
        try:
            out[code] = str((await get_rate(base, code, db)).rate)
        except FxError:
            continue
    return out


def purge_stale_rates(db: Session, older_than_days: int = 90) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    rows = db.execute(select(ExchangeRate).where(ExchangeRate.fetched_at < cutoff)).scalars().all()
    for row in rows:
        db.delete(row)
    return len(rows)
