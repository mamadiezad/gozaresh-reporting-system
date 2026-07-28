"""FastAPI dependencies: authentication, RBAC, request context, rate limiting."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_token, role_has_permission, verify_api_key
from app.models.enums import UserRole
from app.models.user import ApiKey, User

bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


# --------------------------------------------------------------------------
# Rate limiting (in-memory sliding window; use Redis in a cluster)
# --------------------------------------------------------------------------
_hits: dict[str, deque[float]] = defaultdict(deque)


def rate_limit(request: Request) -> None:
    if settings.ENV == "test":
        return
    key = request.client.host if request.client else "unknown"
    window_start = time.monotonic() - 60
    bucket = _hits[key]
    while bucket and bucket[0] < window_start:
        bucket.popleft()
    if len(bucket) >= settings.RATE_LIMIT_PER_MINUTE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded — slow down.",
            headers={"Retry-After": "60"},
        )
    bucket.append(time.monotonic())


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------
def _unauthorised(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> User:
    """Accept either a JWT bearer token or a machine API key."""
    if x_api_key:
        rows = db.execute(select(ApiKey).where(ApiKey.is_active.is_(True))).scalars().all()
        for record in rows:
            if verify_api_key(x_api_key, record.key_hash):
                if record.expires_at and record.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
                    raise _unauthorised("API key expired")
                record.last_used_at = datetime.now(UTC)
                service_user = db.execute(select(User).where(User.username == "svc-integration")).scalar_one_or_none()
                if service_user is None:
                    raise _unauthorised("Service account 'svc-integration' is not provisioned")
                return service_user
        raise _unauthorised("Invalid API key")

    if credentials is None:
        raise _unauthorised("Missing credentials")

    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except ValueError as exc:
        raise _unauthorised(str(exc)) from exc

    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise _unauthorised("User not found or deactivated")
    if user.locked_until and user.locked_until.replace(tzinfo=UTC) > datetime.now(UTC):
        raise HTTPException(status.HTTP_423_LOCKED, detail="Account is temporarily locked")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


# --------------------------------------------------------------------------
# Authorisation
# --------------------------------------------------------------------------
def require_permission(permission: str):
    async def _guard(user: CurrentUser) -> User:
        if not role_has_permission(str(user.role), permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' lacks permission '{permission}'",
            )
        return user

    return _guard


def require_roles(*roles: UserRole):
    allowed = {str(r) for r in roles}

    async def _guard(user: CurrentUser) -> User:
        if str(user.role) not in allowed and str(user.role) != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(sorted(allowed))}",
            )
        return user

    return _guard


# --------------------------------------------------------------------------
# Request context for audit entries
# --------------------------------------------------------------------------
def audit_context(request: Request) -> dict[str, str | None]:
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "request_id": getattr(request.state, "request_id", None),
    }


AuditContext = Annotated[dict, Depends(audit_context)]


def lockout_window() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=settings.LOCKOUT_MINUTES)
