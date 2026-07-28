"""Layered security primitives: password hashing, JWT, field encryption, RBAC."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# --------------------------------------------------------------------------
# Passwords — Argon2id (memory hard) with bcrypt fallback for legacy hashes
# --------------------------------------------------------------------------
pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    deprecated="auto",
    argon2__memory_cost=65536,
    argon2__time_cost=3,
    argon2__parallelism=4,
)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def needs_rehash(hashed: str) -> bool:
    return pwd_context.needs_update(hashed)


class PasswordPolicyError(ValueError):
    """Raised when a password fails the organisational complexity policy."""


def enforce_password_policy(password: str) -> None:
    problems: list[str] = []
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        problems.append(f"at least {settings.PASSWORD_MIN_LENGTH} characters")
    if not any(c.islower() for c in password):
        problems.append("a lowercase letter")
    if not any(c.isupper() for c in password):
        problems.append("an uppercase letter")
    if not any(c.isdigit() for c in password):
        problems.append("a digit")
    if not any(not c.isalnum() for c in password):
        problems.append("a symbol")
    if problems:
        raise PasswordPolicyError("Password must contain " + ", ".join(problems) + ".")


# --------------------------------------------------------------------------
# JWT access / refresh tokens
# --------------------------------------------------------------------------
TokenType = Literal["access", "refresh"]


def create_token(
    subject: str,
    token_type: TokenType = "access",
    *,
    role: str | None = None,
    extra: dict[str, Any] | None = None,
    ttl_minutes: int | None = None,
) -> str:
    now = datetime.now(UTC)
    ttl = ttl_minutes or (
        settings.ACCESS_TOKEN_TTL_MINUTES if token_type == "access" else settings.REFRESH_TOKEN_TTL_MINUTES
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl)).timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    if role:
        payload["role"] = role
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str, *, expected_type: TokenType | None = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:  # pragma: no cover - message varies by lib version
        raise ValueError(f"Invalid token: {exc}") from exc
    if expected_type and payload.get("type") != expected_type:
        raise ValueError(f"Expected {expected_type} token, got {payload.get('type')!r}")
    return payload


# --------------------------------------------------------------------------
# Field-level encryption for PII / bank identifiers (encryption at rest)
# --------------------------------------------------------------------------
def _derive_fernet_key(secret: str, salt: bytes = b"gozaresh-field-v1") -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=390_000)
    return base64.urlsafe_b64encode(kdf.derive(secret.encode()))


_fernet = Fernet(_derive_fernet_key(settings.SECRET_KEY))


def encrypt_field(plaintext: str | None) -> str | None:
    if plaintext is None:
        return None
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_field(ciphertext: str | None) -> str | None:
    if ciphertext is None:
        return None
    return _fernet.decrypt(ciphertext.encode()).decode()


def blind_index(value: str) -> str:
    """Deterministic HMAC so encrypted columns stay searchable by exact match."""
    return hmac.new(settings.SECRET_KEY.encode(), value.strip().lower().encode(), hashlib.sha256).hexdigest()


def mask_secret(value: str, keep: int = 4) -> str:
    if len(value) <= keep:
        return "*" * len(value)
    return "*" * (len(value) - keep) + value[-keep:]


# --------------------------------------------------------------------------
# RBAC
# --------------------------------------------------------------------------
ROLE_HIERARCHY: dict[str, int] = {
    "viewer": 10,
    "requester": 20,
    "finance_manager": 30,
    "inspector": 40,
    "ceo": 50,
    "auditor": 45,
    "admin": 100,
}

PERMISSIONS: dict[str, set[str]] = {
    "viewer": {"report:read", "dashboard:read"},
    "requester": {"report:read", "report:create", "dashboard:read"},
    "finance_manager": {
        "report:read",
        "report:create",
        "report:approve:finance_manager",
        "dashboard:read",
        "alert:read",
    },
    "inspector": {
        "report:read",
        "report:approve:inspector",
        "dashboard:read",
        "alert:read",
        "audit:read",
    },
    "ceo": {
        "report:read",
        "report:approve:ceo",
        "dashboard:read",
        "alert:read",
        "audit:read",
    },
    "auditor": {"report:read", "dashboard:read", "audit:read", "audit:verify"},
    "admin": {"*"},
}


def role_has_permission(role: str, permission: str) -> bool:
    grants = PERMISSIONS.get(role, set())
    return "*" in grants or permission in grants


def generate_api_key() -> tuple[str, str]:
    """Return (plaintext_key, stored_hash) for machine-to-machine clients."""
    raw = "gzk_" + secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def verify_api_key(raw: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hashlib.sha256(raw.encode()).hexdigest(), stored_hash)
