"""Authentication: register, login (with lockout), refresh, profile."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import AuditContext, CurrentUser, DbSession, lockout_window
from app.core.config import settings
from app.core.security import (
    PasswordPolicyError,
    blind_index,
    create_token,
    decode_token,
    encrypt_field,
    enforce_password_policy,
    hash_password,
    verify_password,
)
from app.core.signing import ensure_keypair
from app.models.enums import AuditAction, UserRole
from app.models.user import User
from app.schemas import LoginRequest, RefreshRequest, TokenPair, UserCreate, UserOut
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_tokens(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_token(
            str(user.id),
            "access",
            role=str(user.role),
            extra={"username": user.username},
        ),
        refresh_token=create_token(str(user.id), "refresh", role=str(user.role)),
        expires_in_minutes=settings.ACCESS_TOKEN_TTL_MINUTES,
        user=UserOut.model_validate(user),
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: DbSession, ctx: AuditContext):
    """Self-service registration (privileged roles require an admin — see /users)."""
    try:
        enforce_password_policy(payload.password)
    except PasswordPolicyError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    exists = db.execute(
        select(User).where((User.username == payload.username) | (User.email == payload.email))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Username or email already registered")

    role = payload.role if payload.role in {UserRole.REQUESTER, UserRole.VIEWER} else UserRole.REQUESTER
    key_id = f"user-{payload.username}"
    user = User(
        username=payload.username,
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=role,
        phone_encrypted=encrypt_field(payload.phone) if payload.phone else None,
        phone_index=blind_index(payload.phone) if payload.phone else None,
        signing_key_id=key_id,
        public_key_pem=ensure_keypair(key_id),
    )
    db.add(user)
    db.flush()

    audit.record(
        db,
        action=AuditAction.CREATE,
        entity_type="user",
        entity_id=user.id,
        summary=f"User {user.username} registered with role {user.role}",
        actor_id=user.id,
        actor_username=user.username,
        actor_role=str(user.role),
        after={"username": user.username, "email": user.email, "role": str(user.role)},
        **ctx,
    )
    return user


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, db: DbSession, ctx: AuditContext):
    """Password login with progressive lockout after repeated failures."""
    user = db.execute(select(User).where(User.username == payload.username)).scalar_one_or_none()

    if user is None:
        audit.record(
            db,
            action=AuditAction.LOGIN_FAILED,
            entity_type="user",
            summary=f"Login attempt for unknown username {payload.username!r}",
            actor_username=payload.username,
            **ctx,
        )
        # Commit before raising: the request dependency rolls back on HTTP errors,
        # and a failed-login trail must survive regardless of the response.
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if user.locked_until and user.locked_until.replace(tzinfo=UTC) > datetime.now(UTC):
        raise HTTPException(
            status.HTTP_423_LOCKED,
            detail=f"Account locked until {user.locked_until:%H:%M} UTC",
        )

    if not verify_password(payload.password, user.hashed_password):
        user.failed_login_attempts += 1
        summary = f"Failed login #{user.failed_login_attempts} for {user.username}"
        if user.failed_login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
            user.locked_until = lockout_window()
            summary += f" — account locked for {settings.LOCKOUT_MINUTES} minutes"
        db.flush()
        audit.record(
            db,
            action=AuditAction.LOGIN_FAILED,
            entity_type="user",
            entity_id=user.id,
            summary=summary,
            actor_id=user.id,
            actor_username=user.username,
            actor_role=str(user.role),
            **ctx,
        )
        db.commit()  # persist the attempt counter + lockout even though we 401
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Account is deactivated")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.now(UTC)
    db.flush()

    audit.record(
        db,
        action=AuditAction.LOGIN,
        entity_type="user",
        entity_id=user.id,
        summary=f"{user.username} signed in",
        actor_id=user.id,
        actor_username=user.username,
        actor_role=str(user.role),
        **ctx,
    )
    return _issue_tokens(user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, db: DbSession):
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    user = db.get(User, int(claims["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User not found or deactivated")
    return _issue_tokens(user)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(user: CurrentUser, db: DbSession, ctx: AuditContext):
    audit.record(
        db,
        action=AuditAction.LOGOUT,
        entity_type="user",
        entity_id=user.id,
        summary=f"{user.username} signed out",
        actor_id=user.id,
        actor_username=user.username,
        actor_role=str(user.role),
        **ctx,
    )


@router.get("/users", response_model=list[UserOut])
async def list_users(db: DbSession, user: CurrentUser):
    """Admins see everyone; other roles see only themselves."""
    if str(user.role) == UserRole.ADMIN:
        return list(db.execute(select(User).order_by(User.id)).scalars().all())
    return [user]
