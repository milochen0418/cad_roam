#!/usr/bin/env bash
set -euo pipefail

SUITE_NAME="${1:-}"
if [[ -z "$SUITE_NAME" ]]; then
  echo "Usage: $0 <suite_name>" >&2
  echo "Example: $0 smoke_home" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUITE_DIR="$ROOT_DIR/testcases/$SUITE_NAME"
TEST_SCRIPT="$SUITE_DIR/run_test.py"
# Screenshots and logs (keep them outside the repo when a re-ddns dev-mode install of this
# checkout is running: it hot-reloads on changes under testcases/).
OUTPUT_DIR="${OUTPUT_DIR:-$SUITE_DIR/output}"

if [[ ! -f "$TEST_SCRIPT" ]]; then
  echo "Test suite not found: $TEST_SCRIPT" >&2
  exit 2
fi

mkdir -p "$OUTPUT_DIR"

# Ports of the local server (other apps on this machine may hold 3000/8000).
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
# Prefer IPv4 loopback to avoid IPv6/localhost quirks.
BASE_URL="${BASE_URL:-http://127.0.0.1:$FRONTEND_PORT}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:$BACKEND_PORT}"
export BASE_URL BACKEND_URL OUTPUT_DIR
# Screenshots written into testcases/*/output must not hot-reload the backend (a reload drops
# every world socket).
export REFLEX_HOT_RELOAD_EXCLUDE_PATHS="$ROOT_DIR/testcases"
export REFLEX_TELEMETRY_ENABLED=false
# A fresh collections tree (testcases/fixtures.py) and CAD Roam home in the suite's output folder:
# the suites never see your real models.
if [[ -z "${DDNS_COLLECTIONS_ROOT:-}" ]]; then
  export DDNS_COLLECTIONS_ROOT="$OUTPUT_DIR/collections"
  rm -rf "$DDNS_COLLECTIONS_ROOT"
  run_fixtures=1
fi
if [[ -z "${CAD_ROAM_HOME:-}" ]]; then
  export CAD_ROAM_HOME="$OUTPUT_DIR/home"
  rm -rf "$CAD_ROAM_HOME"
fi
export DDNS_APP_ID="${DDNS_APP_ID:-cad-roam}"
# A suite's own server settings: KEY=value lines in testcases/<suite>/server.env (e.g. a lower
# triangle limit).
if [[ -f "$SUITE_DIR/server.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$SUITE_DIR/server.env"
  set +a
fi

run_in_poetry_env() {
  if [[ -n "${POETRY_ACTIVE:-}" ]]; then
    "$@"
  else
    poetry run "$@"
  fi
}

REFLEX_LOG="$OUTPUT_DIR/reflex.log"
TEST_LOG="$OUTPUT_DIR/test.log"


cleanup() {
  set +e
  if [[ -n "${SERVER_PID:-}" ]]; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" >/dev/null 2>&1 || true
  fi
  # Also ensure ports are freed.
  lsof -ti:"$FRONTEND_PORT,$BACKEND_PORT" 2>/dev/null | xargs -r kill -9 >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[runner] suite=$SUITE_NAME"
echo "[runner] base_url=$BASE_URL"
echo "[runner] output_dir=$OUTPUT_DIR"

if [[ -n "${run_fixtures:-}" ]]; then
  run_in_poetry_env python "$ROOT_DIR/testcases/fixtures.py" "$DDNS_COLLECTIONS_ROOT"
fi

echo "[runner] starting server via ./reflex_rerun.sh ..."
(
  cd "$ROOT_DIR"
  # Ensure we don't double-wrap poetry: reflex_rerun.sh already handles POETRY_ACTIVE.
  if [[ "$FRONTEND_PORT" == "3000" && "$BACKEND_PORT" == "8000" ]]; then
    ./reflex_rerun.sh
  else
    REFLEX_API_URL="http://localhost:$BACKEND_PORT" run_in_poetry_env \
      reflex run --frontend-port "$FRONTEND_PORT" --backend-port "$BACKEND_PORT"
  fi
) >"$REFLEX_LOG" 2>&1 &
SERVER_PID=$!

echo "[runner] waiting for server to be reachable..."
READY=0
for i in $(seq 1 240); do
  code="$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL" || true)"
  if [[ "$code" =~ ^2|^3 ]]; then
    READY=1
    break
  fi
  sleep 1
  # Surface a tiny bit of log if it looks stuck.
  if [[ $i -eq 30 || $i -eq 90 || $i -eq 150 || $i -eq 210 ]]; then
    echo "[runner] still waiting (attempt $i/240), last_http=$code" >&2
  fi
  if ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    echo "[runner] server process exited early; see $REFLEX_LOG" >&2
    exit 1
  fi
done

if [[ "$READY" -ne 1 ]]; then
  echo "[runner] server not ready after timeout; see $REFLEX_LOG" >&2
  exit 1
fi

echo "[runner] running test: $TEST_SCRIPT"
set +e
run_in_poetry_env python "$TEST_SCRIPT" >"$TEST_LOG" 2>&1
TEST_EXIT=$?
set -e

if [[ $TEST_EXIT -ne 0 ]]; then
  echo "[runner] FAIL (exit=$TEST_EXIT). Artifacts in: $OUTPUT_DIR" >&2
  echo "[runner] tail test.log:" >&2
  tail -n 80 "$TEST_LOG" >&2 || true
  exit "$TEST_EXIT"
fi

echo "[runner] PASS. Artifacts in: $OUTPUT_DIR"
