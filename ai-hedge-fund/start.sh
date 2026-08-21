#!/usr/bin/env bash
#
# Start the whole stack: FastAPI on :8000, Vite on :5173.
#
#   ./start.sh
#
# Ctrl-C stops both. Nothing is hosted — the API, the SQLite book and the model
# all run here, which is why this script exists rather than a deploy.
set -euo pipefail

cd "$(dirname "$0")"

BACKEND_PORT=8000
FRONTEND_PORT=5173

say()  { printf '\033[1;36m▸\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m!\033[0m %s\n' "$1"; }
die()  { printf '\033[1;31m✗\033[0m %s\n' "$1" >&2; exit 1; }

command -v uv  >/dev/null || die "uv is not installed — https://docs.astral.sh/uv/"
command -v npm >/dev/null || die "npm is not installed — https://nodejs.org"

# --- preflight ---------------------------------------------------------
OLLAMA_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
WANT_MODEL="$(grep -E '^OLLAMA_MODEL=' .env 2>/dev/null | cut -d= -f2- || echo 'qwen3:30b')"

if curl -sf --max-time 3 "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
  if curl -sf --max-time 3 "$OLLAMA_URL/api/tags" | grep -q "\"$WANT_MODEL\""; then
    say "Ollama up, $WANT_MODEL ready"
  else
    warn "Ollama is up but $WANT_MODEL is not pulled — run: ollama pull $WANT_MODEL"
    warn "Market data, portfolio and backtests still work; AI research will not."
  fi
else
  warn "Ollama unreachable at $OLLAMA_URL — run 'ollama serve', or install from https://ollama.com"
  warn "Everything except AI research still works."
fi

for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
  if lsof -ti tcp:"$port" >/dev/null 2>&1; then
    die "Port $port is already in use. Stop it first:  lsof -ti tcp:$port | xargs kill"
  fi
done

[ -d frontend/node_modules ] || { say "Installing frontend deps…"; (cd frontend && npm install); }

# --- run ---------------------------------------------------------------
PIDS=()
cleanup() {
  printf '\n'
  say "Stopping…"
  for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

say "Starting API on :$BACKEND_PORT"
uv run uvicorn hedge_fund.api.main:app --host 127.0.0.1 --port "$BACKEND_PORT" --reload &
PIDS+=($!)

# Wait for the API before starting the UI, so the first page load is not a
# spurious "backend not reachable".
for _ in $(seq 1 60); do
  curl -sf --max-time 2 "http://127.0.0.1:$BACKEND_PORT/api/health" >/dev/null 2>&1 && break
  sleep 1
done

say "Starting UI on :$FRONTEND_PORT"
(cd frontend && npm run dev -- --port "$FRONTEND_PORT") &
PIDS+=($!)

printf '\n'
say "Open  http://localhost:$FRONTEND_PORT"
say "API   http://127.0.0.1:$BACKEND_PORT/api/health"
printf '  Ctrl-C to stop both.\n\n'

wait
