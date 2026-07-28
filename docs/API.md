# API Reference

Base URL: `http://localhost:8000/api/v1`
Interactive docs: [`/docs`](http://localhost:8000/docs) (Swagger) · [`/redoc`](http://localhost:8000/redoc)

All timestamps are ISO-8601 UTC. All monetary values are returned as **strings** to
preserve the full 16-decimal precision — never parse them into a JS `number` before
doing arithmetic.

---

## Authentication

Two mechanisms are supported:

| Mechanism | Header | Use case |
|---|---|---|
| JWT bearer | `Authorization: Bearer <access_token>` | Interactive users |
| API key | `X-API-Key: gzk_...` | Machine-to-machine (ERP integrations) |

Access tokens live 30 minutes; refresh tokens 7 days.

### `POST /auth/register`

```json
{
  "username": "alice",
  "email": "alice@example.com",
  "password": "Str0ng&Passphrase",
  "full_name": "Alice Rezaei",
  "phone": "09121234567"
}
```

Self-registration only grants `requester` or `viewer`. Privileged roles must be
assigned by an admin. Password policy: ≥10 chars, upper, lower, digit, symbol.

### `POST /auth/login`

```json
{ "username": "bob", "password": "DemoPass!2024" }
```

Returns `access_token`, `refresh_token`, and the user object.
After 5 failed attempts the account locks for 15 minutes and returns `423`.

### `POST /auth/refresh`

```json
{ "refresh_token": "eyJ..." }
```

---

## Calculations

### `POST /calculations/preview`

Stateless calculation — nothing is persisted.

```json
{
  "principal": "25000000000",
  "annual_rate_percent": "23.5",
  "term_months": 36,
  "compounding_per_year": 12,
  "currency": "IRR",
  "convert_to": "USD",
  "frequency": "monthly",
  "with_schedule": true
}
```

Response (abridged):

```json
{
  "principal": "25000000000.0000000000000000",
  "total_interest": "10073724956.0907521651099565",
  "total_payable": "35073724956.0907521651099565",
  "periodic_payment": "974270137.6691875601419432",
  "effective_annual_rate": "0.2618465326962527",
  "display_total": "35073724956",
  "fx_rate": "0.0000017021276596",
  "amount_in_base": "59699.9573729648647480",
  "fx_source": "offline_fixture",
  "duration_ms": 0.83,
  "within_sla": true,
  "sla_ms": 50.0,
  "schedule": [ { "number": 1, "due_date": "2026-08-28", "amount": "...", "...": "..." } ]
}
```

Response headers: `X-Calc-Duration-Ms`, `X-Calc-SLA-Met`.

| Field | Meaning |
|---|---|
| `frequency` | `monthly` \| `quarterly` \| `semiannual` \| `annual` |
| `effective_annual_rate` | `(1 + r/n)^n − 1`, as a fraction |
| `display_total` | Rounded to the currency's real minor unit (IRR → 0 dp, USD → 2 dp) |
| `within_sla` | Whether the computation met the 50 ms target |

### `GET /calculations/rates/{base}/{quote}`

```json
{
  "base": "USD", "quote": "IRR", "rate": "587500.0000000000000000",
  "source": "central_bank", "fetched_at": "2026-07-28T12:00:00+00:00",
  "is_stale": false, "latency_ms": 0.42
}
```

Provider chain: central bank → exchange API → last-known-good from DB (`is_stale: true`).
Set `FX_OFFLINE_MODE=true` for deterministic fixtures (default in demos and CI).

### `GET /calculations/rates/{base}` · `POST /calculations/convert` · `GET /calculations/benchmark`

Full rate table, one-off conversion, and an SLA benchmark returning p50/p95/p99.

---

## Reports & Workflow

### `POST /reports`

```json
{
  "title": "Working capital facility",
  "description": "Q3 credit line",
  "report_type": "loan",
  "principal": "12500000000",
  "currency": "IRR",
  "annual_rate_percent": "23.5",
  "term_months": 24,
  "start_date": "2026-08-01",
  "department": "Treasury",
  "counterparty": "Acme Industrial Co.",
  "auto_calculate": true
}
```

`report_type`: `loan` · `installment` · `investment` · `expense` · `invoice` · `settlement`

Creating a report automatically:
1. converts to the base currency and computes interest + schedule,
2. persists every installment row,
3. pre-builds the three approval stages,
4. checks the amount against the currency's limit and raises an alert if exceeded,
5. writes an audit entry and broadcasts `report.created` over WebSocket.

### `GET /reports`

Query: `page`, `page_size`, `status`, `report_type`, `currency`, `search`.
Requesters see only their own reports; approvers and auditors see everything.

### `GET /reports/inbox`

Reports currently waiting on the caller's role.

### `POST /reports/{id}/submit`

`draft` → `pending_finance`. Requires a completed calculation. Only the creator (or an admin) may submit.

### `POST /reports/{id}/decision`

```json
{ "approved": true, "comment": "Approved under policy 4.2" }
```

| Condition | Result |
|---|---|
| Correct role for the current stage | Decision recorded and signed |
| Wrong role, or stage skipping | `409 Conflict` |
| `approved: false` | Report → `rejected`, later stages → `skipped` |
| Final stage approved | Report → `approved`, `completed_at` set |

### `GET /reports/{id}/signatures`

Re-verifies every stored signature against the **current** report content:

```json
{
  "report_reference": "GZR-202607-E0F644",
  "content_unchanged": true,
  "all_valid": true,
  "steps": [
    { "stage": "finance_manager", "signed": true, "valid": true,
      "approver": "bob", "key_fingerprint": "a1b2c3..." }
  ]
}
```

If anyone edits the amount after approval, `content_unchanged` and `valid` both turn `false`.

### `GET /reports/{id}/workflow` · `GET /reports/{id}/installments` · `POST /reports/{id}/installments/{n}/pay`

---

## Dashboard

### `GET /dashboard/overview`

One round-trip payload with eight sections: `kpis`, `status_breakdown`,
`currency_exposure`, `monthly_trend`, `workflow_throughput`,
`upcoming_installments`, `integration_health`, `alerts`.

Individual endpoints also exist: `/dashboard/kpis`, `/dashboard/charts/status`,
`/dashboard/charts/currency`, `/dashboard/charts/trend`,
`/dashboard/charts/throughput`, `/dashboard/upcoming`, `/dashboard/integrations`.

### `WS /ws/dashboard?token=<access_token>`

Authenticated live channel. Send `ping` → `pong`, `refresh` → fresh KPI snapshot.

Events pushed by the server:

| Event | Fired when |
|---|---|
| `snapshot` | On connect |
| `report.created` | A new report is registered |
| `workflow.pending` | A stage becomes someone's responsibility |
| `workflow.updated` | Any approve/reject decision |
| `workflow.completed` | Final approval or rejection |
| `alert.raised` | Any detector fires |
| `installment.paid` | An installment is settled |

```json
{
  "event": "alert.raised",
  "topic": "dashboard",
  "timestamp": "2026-07-28T12:00:00+00:00",
  "data": { "id": 12, "severity": "critical", "title": "Transaction above limit — GZR-..." }
}
```

---

## Alerts

`GET /alerts` — filter by `acknowledged`, `severity`, `kind`, `limit`.

Kinds: `overdue_installment` · `out_of_range_transaction` · `anomaly` ·
`workflow_stalled` · `integration_failure` · `security`

`POST /alerts/scan` runs every detector immediately.
`POST /alerts/{id}/acknowledge` marks one as handled.

Default per-currency limits (`services/alerts.py`): IRR 50 bn, USD/EUR 100 k, AED 400 k, GBP 80 k.
Anomaly detection uses a modified z-score (MAD-based, robust to outliers) with a
default threshold of 3.0 and a minimum sample of 8 reports per currency.

---

## Audit

All routes require the `audit:read` permission (`inspector`, `ceo`, `auditor`, `admin`).

| Endpoint | Purpose |
|---|---|
| `GET /audit/logs` | Filter by `entity_type`, `entity_id`, `action`, `actor_username` |
| `GET /audit/verify` | Recompute the whole hash chain |
| `GET /audit/stats` | Totals grouped by action |
| `GET /audit/trail/{entity_type}/{entity_id}` | Full history of one entity |
| `GET /audit/export?fmt=csv\|json` | Export for SIEM / WORM archival |

`GET /audit/verify` when the chain is intact:

```json
{ "valid": true, "checked": 45, "broken_at_sequence": null, "head_hash": "4c3ea7..." }
```

After someone tampers with row 2 directly in the database:

```json
{
  "valid": false, "checked": 45, "broken_at_sequence": 2,
  "reason": "entry_hash mismatch — this entry's content was modified"
}
```

---

## Integrations

All connectors are **idempotent** (key = hash of the payload), retry with exponential
backoff on 5xx/network errors, fail fast on 4xx, and log every attempt to `integration_logs`.

### Tax authority (سامانه مودیان)

| Endpoint | Purpose |
|---|---|
| `GET /integrations/moadian/{id}/preview` | Inspect the invoice envelope before sending |
| `POST /integrations/moadian/{id}/submit` | Sign and transmit (report must be `approved`) |
| `POST /integrations/moadian/inquiry` | Check status by `uid` |

The invoice includes VAT at 9% and is signed with an RSA key before transmission.

### Bank gateway

| Endpoint | Purpose |
|---|---|
| `POST /integrations/bank/{id}/settle` | Request settlement (validates IBAN via mod-97) |
| `POST /integrations/bank/{id}/confirm` | Confirm by `tracking_id` |
| `GET /integrations/bank/validate-iban` | Standalone IBAN check |

### Accounting / ERP

| Endpoint | Purpose |
|---|---|
| `GET /integrations/accounting/{id}/voucher.json` | Double-entry voucher as JSON |
| `GET /integrations/accounting/{id}/voucher.xml` | Same document as standard XML |
| `POST /integrations/accounting/{id}/push` | Post to the ledger (rejects unbalanced vouchers) |
| `POST /integrations/accounting/import-xml` | Inbound channel for partner ERPs |

```xml
<?xml version="1.0" encoding="UTF-8"?>
<AccountingVoucher xmlns="urn:gozaresh:accounting:1.0">
  <Header>
    <Number>GZR-202607-E0F644</Number>
    <Date>2026-07-28</Date>
    <Currency>IRR</Currency>
  </Header>
  <Lines>
    <Line no="1">
      <Account>1310</Account>
      <Description>Receivable / principal</Description>
      <Debit>12500000000</Debit>
      <Credit>0</Credit>
    </Line>
  </Lines>
  <Totals><Debit>15786561648</Debit><Credit>15786561648</Credit></Totals>
</AccountingVoucher>
```

---

## Errors

| Code | Meaning |
|---|---|
| `401` | Missing, invalid or expired credentials |
| `403` | Authenticated but the role lacks the permission |
| `409` | Illegal workflow transition (wrong stage, already submitted, not approved yet) |
| `422` | Validation failure (includes a per-field `errors` array) |
| `423` | Account locked after repeated failed logins |
| `429` | Rate limit exceeded (default 240 req/min per IP) |
| `502` | An upstream provider (FX, tax, bank) failed |

Every response carries `X-Request-ID`; the same value appears in error bodies and
audit entries, so a user-reported failure can be traced end to end.
