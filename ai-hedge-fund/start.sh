#!/usr/bin/env bash
#
# Start the whole stack: FastAPI on :8000, Vite on :5173.
#
#   ./start.sh            desk only, on this machine
#   ./start.sh --phone    desk plus a URL your phone can open on the same Wi-Fi
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

# --phone puts the UI on every interface so a phone on the same Wi-Fi can reach
# it. The API stays on 127.0.0.1 either way: the UI proxies /api from this
# machine, so the phone never needs a route to the backend, and binding it
# would expose the book and the model to the whole network for no gain.
PHONE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --api-port) BACKEND_PORT="$2"; shift 2 ;;
    --ui-port)  FRONTEND_PORT="$2"; shift 2 ;;
    --phone)    PHONE=1; shift ;;
    -h|--help)
      cat <<'USAGE'
Usage: ./start.sh [--phone] [--api-port N] [--ui-port N]

Starts the FastAPI backend and the Vite dev server, then stops both on Ctrl-C.
Defaults: API 8000, UI 5173. The UI proxies /api to whichever API port is set.

--phone also serves the UI on this machine's Wi-Fi address and prints the URL
to open on the phone. The API is never exposed; the UI proxies to it locally.
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

# -sTCP:LISTEN matters: without it this matches *any* socket on the port,
# including a long-dead browser connection in CLOSED state, and the script
# then refuses to start over a port that is in fact free.
for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
  if lsof -ti tcp:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
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

LAN_IP=""
if [ "$PHONE" = "1" ]; then
  # Try the interface that carries the default route first, then the usual
  # hardware ones. Only enN is considered: with a VPN connected the default
  # route is a utunN tunnel, and the address on that side of the tunnel is not
  # one the phone on this Wi-Fi can reach.
  LAN_DEFAULT="$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')"
  for iface in "$LAN_DEFAULT" en0 en1 en2; do
    case "$iface" in en[0-9]*) ;; *) continue ;; esac
    LAN_IP="$(ipconfig getifaddr "$iface" 2>/dev/null || true)"
    [ -n "$LAN_IP" ] && break
  done
  [ -n "$LAN_IP" ] || warn "No Wi-Fi address found — is this machine on a network?"
fi

say "Starting UI on :$FRONTEND_PORT"
if [ "$PHONE" = "1" ]; then
  (cd frontend && npm run dev -- --host 0.0.0.0) &
else
  (cd frontend && npm run dev) &
fi
PIDS+=($!)

printf '\n'
say "Open  http://localhost:$FRONTEND_PORT"
if [ -n "$LAN_IP" ]; then
  printf '\n'
  printf '  \033[1;32mOn your phone, same Wi-Fi:  http://%s:%s\033[0m\n' "$LAN_IP" "$FRONTEND_PORT"
  LAN_NAME="$(scutil --get LocalHostName 2>/dev/null || true)"
  if [ -n "$LAN_NAME" ]; then
    # The name holds when the router hands out a different address, so this is
    # the one worth saving to the home screen.
    printf '  \033[1;32mor, address-proof:          http://%s.local:%s\033[0m\n' "$LAN_NAME" "$FRONTEND_PORT"
  fi
  printf '  Then Share -> Add to Home Screen to get an app icon.\n'
fi
say "API   http://127.0.0.1:$BACKEND_PORT/api/health"
printf '  Ctrl-C to stop both.\n\n'

wait
