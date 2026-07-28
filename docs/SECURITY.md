# Security Model

Defence in depth across seven layers, and a tamper-evident audit trail underneath
all of them. This document describes what is implemented, what is deliberately
simplified for a reference repository, and what must change before production.

---

## 1. Authentication

| Control | Implementation |
|---|---|
| Password hashing | **Argon2id** — 64 MB memory cost, 3 iterations, 4 lanes (`core/security.py`) |
| Legacy support | bcrypt kept in the `CryptContext` so old hashes upgrade transparently |
| Password policy | ≥10 chars with upper, lower, digit and symbol; rejected with a specific message |
| Tokens | JWT HS256 — 30 min access, 7 day refresh, each with a unique `jti` |
| Machine access | SHA-256 hashed API keys, compared with `hmac.compare_digest` |
| Brute force | 5 failed attempts → 15 minute lock, counted per account |

**A subtle bug worth noting:** raising an `HTTPException` rolls back the request's
database session, which silently discarded both the failed-login audit entry *and*
the attempt counter — meaning the lockout never triggered. The login route now
commits before raising. Regression test:
`test_audit.py::TestAuditApi::test_account_locks_after_repeated_failures`.

---

## 2. Authorisation (RBAC)

Seven roles with an explicit permission matrix (`core/security.py::PERMISSIONS`):

| Role | Key permissions |
|---|---|
| `viewer` | `report:read`, `dashboard:read` |
| `requester` | + `report:create` |
| `finance_manager` | + `report:approve:finance_manager`, `alert:read` |
| `inspector` | + `report:approve:inspector`, `audit:read` |
| `ceo` | + `report:approve:ceo`, `audit:read` |
| `auditor` | `audit:read`, `audit:verify` (read-only everywhere else) |
| `admin` | `*` |

Enforced in three places:

1. **Route level** — `Depends(require_permission("audit:read"))`
2. **Workflow level** — `workflow.can_act()` checks the role against the current stage
3. **Query level** — requesters only ever see rows where `created_by_id == their id`

---

## 3. Data protection

| Data | Protection |
|---|---|
| Phone numbers, national IDs | **Fernet** (AES-128-CBC + HMAC), key derived via PBKDF2-HMAC-SHA256 with 390 000 iterations |
| Searchability | HMAC-SHA256 **blind index** — exact-match lookups without decrypting |
| Passwords | Argon2id, never reversible |
| Audit payloads | Credentials and PII are redacted before storage |

Ciphertext is non-deterministic (a random IV per encryption), so identical plaintexts
produce different ciphertexts — which is exactly why the blind index exists.

Redacted keys: `password`, `hashed_password`, `token`, `access_token`, `refresh_token`,
`secret`, `api_key`, `national_id`, `authorization`, and their encrypted variants.

---

## 4. Digital signatures

Every approval decision is signed with **RSA-2048 / RSA-PSS / SHA-256** (MGF1, max salt).

The signed payload binds the decision to the report's financial substance:

```python
{
  "report_reference":  "GZR-202607-E0F644",
  "report_content_hash": "<sha256 of principal, currency, rate, term, totals, creator>",
  "stage": "finance_manager",
  "decision": "approved",
  "comment": "...",
  "approver_id": 2,
  "acted_at": "2026-07-28T12:00:00.000000"
}
```

Because the content hash is inside the signature, **editing a report after approval
invalidates every signature on it**. `GET /reports/{id}/signatures` re-verifies against
the current row and reports exactly which stage broke.

Two normalisation issues had to be solved for this to be reliable:

- **Timezone loss** — SQLite returns naive datetimes; timestamps are normalised to
  naive-UTC before hashing.
- **Decimal scale drift** — `Decimal("125")` and `Decimal("125.0000000000000000")`
  are numerically equal but stringify differently, and the DB round-trip changes the
  scale. All amounts pass through `q()` before hashing.

Regression test: `test_workflow.py::TestSignaturePersistence`.

> **Production note:** keys live in a file keystore (`KEYSTORE_DIR`, mode 0600). For
> real deployments move them into an **HSM or cloud KMS** so the private key never
> touches application storage.

---

## 5. Audit trail

An append-only, hash-chained log. Each entry stores:

```
entry_hash = SHA256(previous_hash ‖ canonical_json(entry))
```

`canonical_json` sorts keys and uses fixed separators, so serialisation is
deterministic. The first entry links to a genesis hash of 64 zeros.

**What this detects:**

| Attack | Detection |
|---|---|
| Editing a historical entry | `entry_hash` no longer matches its content |
| Deleting an entry | The next entry's `previous_hash` doesn't match |
| Inserting a forged entry | Sequence numbers and hashes both break |

`GET /audit/verify` recomputes the whole chain and returns the exact
`broken_at_sequence`. Verified in `test_audit.py::TestAuditChain` with tests that
actually mutate and delete rows behind the application's back.

**What it does not defend against:** an attacker who can rewrite *every* subsequent
entry. Mitigate by exporting `head_hash` to append-only external storage (WORM bucket,
SIEM, or a notary service) on a schedule — `GET /audit/export` produces CSV or JSON
for exactly this purpose.

Recorded for each entry: actor (id, username, role), action, entity, before/after
state, IP, user-agent, and the request correlation ID.

---

## 6. Transport & application hardening

| Header | Value |
|---|---|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Content-Security-Policy` | `default-src 'self'; frame-ancestors 'none'` |
| `Referrer-Policy` | `no-referrer` |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=()` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains; preload` (prod only) |

Additional controls:

- **CORS** restricted to an explicit origin allow-list (never `*` with credentials).
- **Rate limiting** — 240 requests/minute per IP, sliding window.
- **Trusted hosts** enforced in production.
- **Request correlation** — every response carries `X-Request-ID`, echoed into audit rows.
- **Error masking** — in production, unhandled exceptions return a generic message plus
  the request ID; stack traces only appear in development.
- **SQL injection** — SQLAlchemy Core/ORM parameterises every query; no string-built SQL.
- **Foreign keys** — enforced on SQLite via `PRAGMA foreign_keys=ON`.

---

## 7. Integration security

- **Idempotency keys** derived from the payload hash prevent duplicate settlements
  if a client retries.
- **HMAC request signing** for bank gateway calls.
- **RSA signing** of tax authority invoice envelopes.
- **Retry policy** distinguishes retryable (5xx, network) from terminal (4xx) failures,
  so a rejected invoice is never blindly re-sent.
- **IBAN mod-97 validation** before any money movement is requested.
- **Sandbox by default** — `INTEGRATIONS_SANDBOX=true` simulates responses so demos and
  CI never reach a real government or banking endpoint.

---

## Production checklist

- [ ] `SECRET_KEY` replaced with `openssl rand -hex 32`
- [ ] `ENV=prod`, `DEBUG=false`
- [ ] PostgreSQL instead of SQLite
- [ ] TLS terminated in front of the app; HSTS verified
- [ ] Signing keys migrated to an HSM/KMS
- [ ] Rate limiting moved to Redis (the in-memory window is per-process)
- [ ] Audit `head_hash` exported to append-only external storage on a schedule
- [ ] `ALLOWED_ORIGINS` narrowed to the real dashboard domain
- [ ] MFA enabled for `ceo`, `admin` and `auditor` (the `mfa_enabled` column is ready; the flow is not implemented)
- [ ] Dependency scanning (`pip-audit`, `npm audit`) wired into CI
- [ ] Log shipping to a SIEM with alerting on `login_failed` spikes

---

## Known limitations

This is a reference implementation. The following are deliberately out of scope:

1. **MFA** — the schema field exists; TOTP enrolment and verification are not built.
2. **Token revocation** — JWTs are stateless; a denylist keyed on `jti` is needed for immediate logout.
3. **Key rotation** — signing keys are created once per user; rotation and re-signing are not automated.
4. **Rate limiting** is per-process and resets on restart.
5. **Schema migrations** use `create_all`; add Alembic before the first production change.
6. **Real integration schemas** — Moadian and bank payloads follow the public shape but
   must be validated against the latest official specification before go-live.

## Reporting a vulnerability

Open a private security advisory on GitHub rather than a public issue.
