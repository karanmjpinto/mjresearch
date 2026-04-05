#!/usr/bin/env bash
# Full local setup: create/link Railway project, public domain, deploy.
# Requires: run `railway login` once (browser).

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! railway whoami &>/dev/null; then
  echo "Not logged in. Run:  railway login"
  exit 1
fi

if ! railway status &>/dev/null; then
  echo "Creating and linking Railway project…"
  railway init -n "mj-ai-hedge-fund"
fi

echo "Ensuring a Railway-provided HTTPS domain…"
railway domain 2>/dev/null || true

echo "Deploying…"
railway up

echo ""
echo "Next: copy your service’s public URL from the Railway dashboard (Networking), then:"
echo "  cd $(pwd)"
echo "  railway variable set FRONTEND_URL=https://YOUR-SERVICE.up.railway.app"
echo ""
echo "Optional Sentry:"
echo "  railway variable set SENTRY_DSN=..."
echo "  railway variable set VITE_SENTRY_DSN=...   # same DSN; triggers rebuild for browser"
echo ""
echo "Open dashboard:  railway open"
