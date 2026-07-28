#!/usr/bin/env bash
#
# End-to-end smoke test against a running Gozaresh API.
#
#   ./scripts/smoke-test.sh [base_url]
#
# Exercises all five headline features and fails loudly on any regression.
set -euo pipefail

BASE="${1:-http://127.0.0.1:8000}"
API="$BASE/api/v1"
PASSWORD="DemoPass!2024"
FAILURES=0

green() { printf '\033[0;32m%s\033[0m\n' "$1"; }
red()   { printf '\033[0;31m%s\033[0m\n' "$1"; }
info()  { printf '\033[0;36m▸ %s\033[0m\n' "$1"; }

check() {
  local label="$1" actual="$2" expected="$3"
  if [[ "$actual" == "$expected" ]]; then
    green "  ✓ $label"
  else
    red   "  ✗ $label (expected '$expected', got '$actual')"
    FAILURES=$((FAILURES + 1))
  fi
}

json() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)"; }

login() {
  curl -sS -X POST "$API/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$1\",\"password\":\"$PASSWORD\"}" | json "d['access_token']"
}

# ---------------------------------------------------------------------------
info "Health check"
STATUS=$(curl -sS "$BASE/health" | json "d['status']")
check "service healthy" "$STATUS" "healthy"

# ---------------------------------------------------------------------------
info "Authentication & RBAC"
FINANCE=$(login bob)
AUDITOR=$(login erin)
REQUESTER=$(login alice)
[[ -n "$FINANCE" ]] && green "  ✓ tokens issued" || { red "  ✗ login failed"; exit 1; }

DENIED=$(curl -sS -o /dev/null -w '%{http_code}' "$API/audit/logs" -H "Authorization: Bearer $REQUESTER")
check "requester denied audit access" "$DENIED" "403"

UNAUTH=$(curl -sS -o /dev/null -w '%{http_code}' "$API/reports")
check "unauthenticated request rejected" "$UNAUTH" "401"

# ---------------------------------------------------------------------------
info "Feature 1 — Decimal precision & 50 ms SLA"
CALC=$(curl -sS -X POST "$API/calculations/preview" \
  -H "Authorization: Bearer $FINANCE" -H 'Content-Type: application/json' \
  -d '{"principal":"25000000000","annual_rate_percent":"23.5","term_months":36,"currency":"IRR","convert_to":"USD"}')

WITHIN_SLA=$(echo "$CALC" | json "str(d['within_sla']).lower()")
check "calculation within SLA" "$WITHIN_SLA" "true"

DECIMALS=$(echo "$CALC" | json "len(d['total_payable'].split('.')[1])")
check "16 decimal places retained" "$DECIMALS" "16"

HAS_FX=$(echo "$CALC" | json "str(d['amount_in_base'] is not None).lower()")
check "multi-currency conversion applied" "$HAS_FX" "true"

BENCH=$(curl -sS "$API/calculations/benchmark?iterations=200" -H "Authorization: Bearer $FINANCE")
SLA_RATIO=$(echo "$BENCH" | json "d['sla_met_ratio']")
check "200/200 iterations under 50 ms" "$SLA_RATIO" "1.0"

# ---------------------------------------------------------------------------
info "Feature 2 — Multi-stage signed workflow"
NEW=$(curl -sS -X POST "$API/reports" -H "Authorization: Bearer $REQUESTER" \
  -H 'Content-Type: application/json' \
  -d '{"title":"Smoke test facility","principal":"750000000","currency":"IRR","annual_rate_percent":"19","term_months":12}')
RID=$(echo "$NEW" | json "d['id']")
STAGES=$(echo "$NEW" | json "len(d['steps'])")
check "three approval stages created" "$STAGES" "3"

curl -sS -X POST "$API/reports/$RID/submit" -H "Authorization: Bearer $REQUESTER" > /dev/null

OUT_OF_ORDER=$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$API/reports/$RID/decision" \
  -H "Authorization: Bearer $(login dave)" -H 'Content-Type: application/json' \
  -d '{"approved":true,"comment":"skipping ahead"}')
check "stage order enforced" "$OUT_OF_ORDER" "409"

for ROLE in bob carol dave; do
  curl -sS -X POST "$API/reports/$RID/decision" -H "Authorization: Bearer $(login $ROLE)" \
    -H 'Content-Type: application/json' -d '{"approved":true,"comment":"approved"}' > /dev/null
done

FINAL=$(curl -sS "$API/reports/$RID" -H "Authorization: Bearer $FINANCE" | json "d['status']")
check "report fully approved" "$FINAL" "approved"

SIGS=$(curl -sS "$API/reports/$RID/signatures" -H "Authorization: Bearer $AUDITOR")
ALL_VALID=$(echo "$SIGS" | json "str(d['all_valid']).lower()")
check "all digital signatures valid" "$ALL_VALID" "true"

UNCHANGED=$(echo "$SIGS" | json "str(d['content_unchanged']).lower()")
check "report content unmodified" "$UNCHANGED" "true"

# ---------------------------------------------------------------------------
info "Feature 3 — Dashboard & alerts"
KPIS=$(curl -sS "$API/dashboard/kpis" -H "Authorization: Bearer $FINANCE")
HAS_KPIS=$(echo "$KPIS" | json "str('total_reports' in d).lower()")
check "KPIs returned" "$HAS_KPIS" "true"

OVERVIEW_KEYS=$(curl -sS "$API/dashboard/overview" -H "Authorization: Bearer $FINANCE" | json "len(d)")
check "overview has 8 sections" "$OVERVIEW_KEYS" "8"

BIG=$(curl -sS -X POST "$API/reports" -H "Authorization: Bearer $REQUESTER" \
  -H 'Content-Type: application/json' \
  -d '{"title":"Out of range probe","principal":"88000000000000","currency":"IRR","annual_rate_percent":"20","term_months":12}')
BIG_ID=$(echo "$BIG" | json "d['id']")
RANGE_ALERT=$(curl -sS "$API/alerts?kind=out_of_range_transaction" -H "Authorization: Bearer $FINANCE" \
  | json "str(any(a['report_id']==$BIG_ID for a in d)).lower()")
check "out-of-range transaction flagged" "$RANGE_ALERT" "true"

# ---------------------------------------------------------------------------
info "Feature 4 — Tax, bank and accounting integrations"
MOADIAN=$(curl -sS -X POST "$API/integrations/moadian/$RID/submit" -H "Authorization: Bearer $FINANCE")
check "tax authority accepted invoice" "$(echo "$MOADIAN" | json "d['status']")" "ACCEPTED"

SETTLE=$(curl -sS -X POST "$API/integrations/bank/$RID/settle" -H "Authorization: Bearer $FINANCE" \
  -H 'Content-Type: application/json' -d '{"iban":"IR820540102680020817909002","description":"smoke"}')
TRACKING=$(echo "$SETTLE" | json "d['tracking_id']")
check "settlement requested" "$(echo "$SETTLE" | json "d['status']")" "PENDING_CONFIRMATION"

CONFIRM=$(curl -sS -X POST "$API/integrations/bank/$RID/confirm" -H "Authorization: Bearer $FINANCE" \
  -H 'Content-Type: application/json' -d "{\"tracking_id\":\"$TRACKING\"}")
check "settlement confirmed by bank" "$(echo "$CONFIRM" | json "d['status']")" "CONFIRMED"

BAD_IBAN=$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$API/integrations/bank/$RID/settle" \
  -H "Authorization: Bearer $FINANCE" -H 'Content-Type: application/json' \
  -d '{"iban":"IR000000000000000000000000"}')
check "invalid IBAN rejected" "$BAD_IBAN" "422"

LEDGER=$(curl -sS -X POST "$API/integrations/accounting/$RID/push" -H "Authorization: Bearer $FINANCE")
check "accounting voucher posted" "$(echo "$LEDGER" | json "d['status']")" "POSTED"

XML_OK=$(curl -sS "$API/integrations/accounting/$RID/voucher.xml" -H "Authorization: Bearer $FINANCE" \
  | head -c 5)
check "XML export well-formed" "$XML_OK" "<?xml"

# ---------------------------------------------------------------------------
info "Feature 5 — Audit trail integrity"
CHAIN=$(curl -sS "$API/audit/verify" -H "Authorization: Bearer $AUDITOR")
check "hash chain intact" "$(echo "$CHAIN" | json "str(d['valid']).lower()")" "true"

ENTRIES=$(echo "$CHAIN" | json "d['checked']")
info "  $ENTRIES audit entries verified"

CSV_HEADER=$(curl -sS "$API/audit/export?fmt=csv" -H "Authorization: Bearer $AUDITOR" | head -1 | cut -c1-8)
check "CSV export works" "$CSV_HEADER" "sequence"

SECURITY_HEADER=$(curl -sS -D- -o /dev/null "$BASE/health" | grep -ci "x-frame-options: DENY" || true)
check "security headers present" "$SECURITY_HEADER" "1"

# ---------------------------------------------------------------------------
echo
if [[ $FAILURES -eq 0 ]]; then
  green "════════════════════════════════════════"
  green " All smoke tests passed ✓"
  green "════════════════════════════════════════"
  exit 0
else
  red "════════════════════════════════════════"
  red " $FAILURES check(s) failed ✗"
  red "════════════════════════════════════════"
  exit 1
fi
