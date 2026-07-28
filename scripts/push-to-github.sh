#!/usr/bin/env bash
#
# Publish this repository to GitHub.
#
#   ./scripts/push-to-github.sh <github-username> [repo-name]
#
# Requires either the GitHub CLI (`gh`) — recommended — or a manual remote.
set -euo pipefail

USER_NAME="${1:-}"
REPO_NAME="${2:-gozaresh-reporting-system}"

if [[ -z "$USER_NAME" ]]; then
  echo "Usage: $0 <github-username> [repo-name]" >&2
  exit 1
fi

cd "$(dirname "$0")/.."

# Refuse to publish if the working tree is dirty.
if [[ -n "$(git status --porcelain)" ]]; then
  echo "✗ Working tree is not clean. Commit or stash your changes first." >&2
  git status --short >&2
  exit 1
fi

echo "▸ Repository : $USER_NAME/$REPO_NAME"
echo "▸ Commits    : $(git rev-list --count HEAD)"
echo "▸ Files      : $(git ls-files | wc -l | tr -d ' ')"
echo

if command -v gh >/dev/null 2>&1; then
  echo "▸ Using the GitHub CLI…"
  gh repo create "$USER_NAME/$REPO_NAME" \
    --public \
    --source=. \
    --remote=origin \
    --description "Enterprise reporting platform: multi-currency Decimal calculations under a 50ms SLA, signed three-stage approval workflow, real-time dashboard, tax/bank integrations and a tamper-evident audit trail." \
    --push
else
  echo "▸ GitHub CLI not found — using plain git."
  echo "  First create an empty repository at: https://github.com/new"
  echo "  (no README, no .gitignore, no license — this repo already has them)"
  echo
  read -rp "  Press Enter once the empty repository exists… " _

  git remote remove origin 2>/dev/null || true
  git remote add origin "https://github.com/$USER_NAME/$REPO_NAME.git"
  git branch -M main
  git push -u origin main
fi

echo
echo "✓ Published: https://github.com/$USER_NAME/$REPO_NAME"
echo
echo "Suggested next steps:"
echo "  • Add topics: fastapi, nextjs, fintech, decimal-precision, audit-trail, rbac"
echo "  • Update the CI badge in README.md — replace OWNER/REPO with $USER_NAME/$REPO_NAME"
echo "  • Enable branch protection on main (require the CI check to pass)"
