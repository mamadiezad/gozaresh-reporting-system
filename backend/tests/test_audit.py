"""Feature #5 — layered security and a tamper-evident audit trail."""

from __future__ import annotations

import pytest

from app.core.security import (
    PasswordPolicyError,
    blind_index,
    decrypt_field,
    encrypt_field,
    enforce_password_policy,
    generate_api_key,
    hash_password,
    role_has_permission,
    verify_api_key,
    verify_password,
)
from app.models.enums import AuditAction
from app.services import audit as audit_service


class TestPasswordSecurity:
    def test_argon2_hash_roundtrip(self):
        hashed = hash_password("TestPass!2024")
        assert hashed.startswith("$argon2")
        assert verify_password("TestPass!2024", hashed)
        assert not verify_password("wrong", hashed)

    def test_hashes_are_salted(self):
        assert hash_password("same") != hash_password("same")

    @pytest.mark.parametrize(
        "bad",
        ["short1!A", "alllowercase1!", "ALLUPPERCASE1!", "NoDigits!!", "NoSymbol123"],
    )
    def test_policy_rejects_weak_passwords(self, bad):
        with pytest.raises(PasswordPolicyError):
            enforce_password_policy(bad)

    def test_policy_accepts_strong_password(self):
        enforce_password_policy("Str0ng&Passphrase")


class TestFieldEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        cipher = encrypt_field("09121234567")
        assert cipher != "09121234567"
        assert decrypt_field(cipher) == "09121234567"

    def test_ciphertext_is_non_deterministic(self):
        assert encrypt_field("secret") != encrypt_field("secret")

    def test_blind_index_is_deterministic(self):
        assert blind_index("09121234567") == blind_index(" 09121234567 ")
        assert blind_index("a") != blind_index("b")


class TestApiKeys:
    def test_generate_and_verify(self):
        raw, stored = generate_api_key()
        assert raw.startswith("gzk_")
        assert verify_api_key(raw, stored)
        assert not verify_api_key("gzk_wrong", stored)


class TestRBAC:
    @pytest.mark.parametrize(
        "role,permission,expected",
        [
            ("admin", "anything:at:all", True),
            ("auditor", "audit:read", True),
            ("auditor", "report:create", False),
            ("requester", "report:create", True),
            ("requester", "audit:read", False),
            ("viewer", "report:create", False),
        ],
    )
    def test_permission_matrix(self, role, permission, expected):
        assert role_has_permission(role, permission) is expected


class TestAuditChain:
    def test_entries_are_linked(self, db):
        first = audit_service.record(db, action=AuditAction.CREATE, entity_type="test", summary="one")
        second = audit_service.record(db, action=AuditAction.UPDATE, entity_type="test", summary="two")
        assert first.sequence == 1 and second.sequence == 2
        assert second.previous_hash == first.entry_hash
        assert first.previous_hash == "0" * 64

    def test_chain_verifies_clean(self, db):
        for i in range(5):
            audit_service.record(db, action=AuditAction.CREATE, entity_type="test", summary=f"entry {i}")
        result = audit_service.verify_chain(db)
        assert result["valid"] is True
        assert result["checked"] == 5

    def test_tampering_is_detected(self, db):
        for i in range(4):
            audit_service.record(db, action=AuditAction.CREATE, entity_type="test", summary=f"entry {i}")
        db.commit()

        from app.models.audit import AuditLog

        victim = db.query(AuditLog).filter(AuditLog.sequence == 2).one()
        victim.summary = "entry 2 — silently rewritten"
        db.commit()

        result = audit_service.verify_chain(db)
        assert result["valid"] is False
        assert result["broken_at_sequence"] == 2
        assert "modified" in result["reason"]

    def test_deletion_is_detected(self, db):
        for i in range(4):
            audit_service.record(db, action=AuditAction.CREATE, entity_type="test", summary=f"entry {i}")
        db.commit()

        from app.models.audit import AuditLog

        db.delete(db.query(AuditLog).filter(AuditLog.sequence == 2).one())
        db.commit()

        result = audit_service.verify_chain(db)
        assert result["valid"] is False
        assert result["broken_at_sequence"] == 3

    def test_secrets_are_redacted(self, db):
        entry = audit_service.record(
            db,
            action=AuditAction.LOGIN,
            entity_type="user",
            summary="login",
            after={"username": "alice", "password": "hunter2", "api_key": "gzk_leak"},
        )
        assert "hunter2" not in entry.after_state
        assert "gzk_leak" not in entry.after_state
        assert "***REDACTED***" in entry.after_state
        assert "alice" in entry.after_state


class TestAuditApi:
    def test_login_is_audited(self, client, auth):
        auth("requester")
        logs = client.get("/api/v1/audit/logs", params={"action": "login"}, headers=auth("auditor")).json()
        assert any(entry["actor_username"] == "alice" for entry in logs)

    def test_failed_login_is_audited(self, client, auth):
        client.post("/api/v1/auth/login", json={"username": "alice", "password": "WrongPass!99"})
        logs = client.get(
            "/api/v1/audit/logs",
            params={"action": "login_failed"},
            headers=auth("auditor"),
        ).json()
        assert len(logs) >= 1

    def test_account_locks_after_repeated_failures(self, client, auth):
        for _ in range(5):
            client.post(
                "/api/v1/auth/login",
                json={"username": "alice", "password": "WrongPass!99"},
            )
        blocked = client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "TestPass!2024"},
        )
        assert blocked.status_code == 423

    def test_requester_cannot_read_audit(self, client, auth):
        assert client.get("/api/v1/audit/logs", headers=auth("requester")).status_code == 403

    def test_chain_endpoint_reports_valid(self, client, auth, sample_report):
        result = client.get("/api/v1/audit/verify", headers=auth("auditor")).json()
        assert result["valid"] is True
        assert result["checked"] > 0

    def test_entity_trail(self, client, auth, sample_report):
        trail = client.get(f"/api/v1/audit/trail/report/{sample_report['id']}", headers=auth("auditor")).json()
        assert len(trail) >= 1
        assert trail[0]["entity_type"] == "report"

    def test_csv_export(self, client, auth, sample_report):
        response = client.get("/api/v1/audit/export", params={"fmt": "csv"}, headers=auth("auditor"))
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "entry_hash" in response.text.splitlines()[0]


class TestSecurityHeaders:
    def test_headers_present(self, client):
        response = client.get("/health")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "Content-Security-Policy" in response.headers
        assert response.headers["X-Request-ID"]

    def test_unauthenticated_is_rejected(self, client):
        assert client.get("/api/v1/reports").status_code == 401

    def test_invalid_token_is_rejected(self, client):
        response = client.get("/api/v1/reports", headers={"Authorization": "Bearer not-a-real-token"})
        assert response.status_code == 401
