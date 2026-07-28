/** English landing-page content, kept separate so the Persian bundle stays small. */

export const FEATURES_EN = [
  {
    id: "calculations",
    title: "Precise real-time multi-currency calculations",
    body:
      "Exchange rates are pulled from authoritative sources (central bank feed, with an " +
      "exchange API fallback), compound interest and instalment schedules are computed in " +
      "Decimal to 16 places, and the final figure returns in under 50 milliseconds.",
    points: [
      "No float anywhere on the monetary path",
      "Provider chain: central bank → exchange API → last-known-good",
      "Measured p99: 1.7 ms for a 60-month loan",
    ],
  },
  {
    id: "workflow",
    title: "Multi-stage approval workflow",
    body:
      "Every submitted request routes automatically to the finance manager, then the " +
      "inspector, then the CEO. Each stage records a complete log entry and an RSA digital " +
      "signature.",
    points: [
      "Stage order is strictly enforced — skipping returns 409",
      "RSA-2048 / PSS signature over the report's content hash",
      "Editing an approved report invalidates every signature",
    ],
  },
  {
    id: "dashboard",
    title: "Live dashboard and instant alerts",
    body:
      "Interactive charts show report status in real time, with automatic detection of " +
      "overdue instalments and out-of-range transactions, and notifications delivered over " +
      "email, SMS and WebSocket.",
    points: [
      "MAD-based statistical anomaly detection",
      "Stalled-approval SLA monitoring",
      "Alerts are deduplicated by key",
    ],
  },
  {
    id: "integrations",
    title: "Tax authority, bank and accounting integrations",
    body:
      "Signed invoices are submitted to the tax authority, settlement confirmations are " +
      "retrieved from the bank gateway, and double-entry vouchers are exchanged with " +
      "accounting software over REST or standard XML/JSON documents.",
    points: [
      "Every call is idempotent (payload-hash keyed)",
      "IBAN validated with the ISO 13616 mod-97 checksum",
      "Exponential backoff, with 4xx treated as terminal",
    ],
  },
  {
    id: "security",
    title: "Layered security and a complete audit trail",
    body:
      "JWT authentication, Argon2id password hashing, role-based access control, " +
      "field-level encryption for personally identifiable data, and a hash-chained audit " +
      "log that exposes any tampering with history.",
    points: [
      "Chain formula: H(previous_hash ‖ canonical(entry))",
      "Verification reports the exact tampered sequence number",
      "Credentials and PII are redacted before they reach the log",
    ],
  },
] as const;

export const FAQ_EN = [
  {
    question: "What problem does this enterprise reporting system solve?",
    answer:
      "It replaces spreadsheet-and-email approval chains with a single auditable flow. Each " +
      "report gets a unique reference, a calculated instalment schedule, a signed approval " +
      "chain and an immutable change history — so finance teams can prove who approved what, " +
      "when, and on which figures.",
  },
  {
    question: "Why use Decimal instead of floating point for money?",
    answer:
      "Binary floats accumulate error: 0.1 + 0.2 is not exactly 0.3. This system keeps the " +
      "entire monetary path in Decimal with banker's rounding at 16 places, so the principal " +
      "components of an amortisation schedule sum back to the original principal exactly. " +
      "A custom SQLAlchemy column type also prevents SQLite from silently coercing those " +
      "values to a C double.",
  },
  {
    question: "How does the digital signature workflow work?",
    answer:
      "Three ordered stages: finance manager, inspector, then CEO. Each decision is signed " +
      "with an RSA-2048 key using PSS padding over a canonical payload that includes a hash " +
      "of the report's financial substance. If anyone edits the amount after approval, every " +
      "signature on that report fails verification and the API reports which stage broke.",
  },
  {
    question: "Can it integrate with tax authorities and banking systems?",
    answer:
      "Yes. Connectors ship for the Iranian tax authority (سامانه مودیان), a bank settlement " +
      "gateway, and accounting/ERP systems via REST JSON or standard XML documents. All " +
      "connectors are idempotent, retry with exponential backoff, and run in sandbox mode by " +
      "default so demos and CI never reach a live endpoint.",
  },
  {
    question: "How does the tamper-evident audit trail work?",
    answer:
      "Each audit entry stores the hash of the previous entry, forming a chain. Editing or " +
      "deleting any historical row breaks the linkage, and the verification endpoint " +
      "recomputes the whole chain and returns the exact sequence number where it broke. " +
      "This is verified by tests that mutate and delete rows behind the application's back.",
  },
  {
    question: "Is it production-ready and open source?",
    answer:
      "It is MIT-licensed and runs via Docker Compose in minutes, with 115 tests at 84% " +
      "coverage and CI running lint, tests and an end-to-end smoke suite. The README " +
      "documents a production checklist — move signing keys to an HSM/KMS, switch to " +
      "PostgreSQL, add Alembic migrations, and move rate limiting to Redis before going live.",
  },
] as const;
