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

# Ports are overridable so a second instance can run beside one already bound:
#   ./start.sh --api-port 8010 --ui-port 5174
#   BACKEND_PORT=8010 FRONTEND_PORT=5174 ./start.sh
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

while [ $# -gt 0 ]; do
  case "$1" in
    --api-port) BACKEND_PORT="$2"; shift 2 ;;
    --ui-port)  FRONTEND_PORT="$2"; shift 2 ;;
    -h|--help)
      cat <<'USAGE'
Usage: ./start.sh [--api-port N] [--ui-port N]

Starts the FastAPI backend and the Vite dev server, then stops both on Ctrl-C.
Defaults: API 8000, UI 5173. The UI proxies /api to whichever API port is set.
USAGE
      exit 0 ;;
    *) printf 'Unknown argument: %s (try --help)\n' "$1" >&2; exit 2 ;;
  esac
done

# The UI proxy reads this, so both halves always agree on the port.
export BACKEND_PORT FRONTEND_PORT

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
    die "Port $port is in use. Either free it (lsof -ti tcp:$port | xargs kill) or pick another:  ./start.sh --api-port 8010 --ui-port 5174"
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
(cd frontend && npm run dev) &
PIDS+=($!)

printf '\n'
say "Open  http://localhost:$FRONTEND_PORT"
say "API   http://127.0.0.1:$BACKEND_PORT/api/health"
printf '  Ctrl-C to stop both.\n\n'

wait
