from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only-not-production")
os.environ.setdefault("FX_OFFLINE_MODE", "true")
os.environ.setdefault("NOTIFICATIONS_DRY_RUN", "true")
os.environ.setdefault("INTEGRATIONS_SANDBOX", "true")
os.environ.setdefault("ENABLE_BACKGROUND_SCHEDULER", "false")

_TMP = Path(tempfile.mkdtemp(prefix="gozaresh-test-"))
os.environ.setdefault("KEYSTORE_DIR", str(_TMP / "keystore"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP / 'test.db'}")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.models.enums import UserRole
from app.models.user import User

TEST_PASSWORD = "TestPass!2024"


@pytest.fixture(scope="function")
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture(scope="function")
def db(engine):
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()
    try:
        yield session
        session.commit()
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(engine):
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def _override():
        session = Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _make_user(session, username: str, role: UserRole, email: str | None = None) -> User:
    user = User(
        username=username,
        email=email or f"{username}@gozaresh-demo.com",
        full_name=username.title(),
        hashed_password=hash_password(TEST_PASSWORD),
        role=role,
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture
def users(engine):
    """One active user for every role in the workflow."""
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()
    created = {
        "requester": _make_user(session, "alice", UserRole.REQUESTER),
        "finance_manager": _make_user(session, "bob", UserRole.FINANCE_MANAGER),
        "inspector": _make_user(session, "carol", UserRole.INSPECTOR),
        "ceo": _make_user(session, "dave", UserRole.CEO),
        "auditor": _make_user(session, "erin", UserRole.AUDITOR),
        "admin": _make_user(session, "root", UserRole.ADMIN),
    }
    ids = {k: v.id for k, v in created.items()}
    session.close()
    return ids


@pytest.fixture
def auth(client, users):
    """Return a helper that yields Authorization headers for any role."""
    tokens: dict[str, str] = {}

    def _headers(role: str) -> dict[str, str]:
        username = {
            "requester": "alice",
            "finance_manager": "bob",
            "inspector": "carol",
            "ceo": "dave",
            "auditor": "erin",
            "admin": "root",
        }[role]
        if role not in tokens:
            response = client.post(
                "/api/v1/auth/login",
                json={"username": username, "password": TEST_PASSWORD},
            )
            assert response.status_code == 200, response.text
            tokens[role] = response.json()["access_token"]
        return {"Authorization": f"Bearer {tokens[role]}"}

    return _headers


@pytest.fixture
def sample_report(client, auth):
    payload = {
        "title": "Working capital facility",
        "description": "Q3 credit line",
        "report_type": "loan",
        "principal": "1000000000",
        "currency": "IRR",
        "annual_rate_percent": "18",
        "term_months": 12,
        "department": "Treasury",
        "counterparty": "Acme Industrial Co.",
    }
    response = client.post("/api/v1/reports", json=payload, headers=auth("requester"))
    assert response.status_code == 201, response.text
    return response.json()
