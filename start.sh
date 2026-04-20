#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

if [ -f ./.env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required but was not found in PATH." >&2
  exit 1
fi

: "${MESHSEER_BIND_HOST:=127.0.0.1}"
: "${MESHSEER_BIND_PORT:=8000}"
: "${MESHSEER_DB_PATH:=./data/meshseer.db}"

mkdir -p -- "$(dirname -- "$MESHSEER_DB_PATH")"

if PRECHECK_OUTPUT=$(uv run python -m meshseer.startup \
  --host "$MESHSEER_BIND_HOST" \
  --port "$MESHSEER_BIND_PORT"); then
  :
else
  PRECHECK_STATUS=$?
  case "$PRECHECK_STATUS" in
    10)
      echo "Meshseer is already running at ${PRECHECK_OUTPUT%/api/health}/"
      exit 0
      ;;
    11)
      echo "Port ${MESHSEER_BIND_PORT} is already in use on ${MESHSEER_BIND_HOST}." >&2
      echo "Stop the existing process or run with MESHSEER_BIND_PORT=<port> ./start.sh" >&2
      exit 1
      ;;
    *)
      [ -n "$PRECHECK_OUTPUT" ] && printf '%s\n' "$PRECHECK_OUTPUT" >&2
      exit "$PRECHECK_STATUS"
      ;;
  esac
fi

echo "Starting Meshseer on ${MESHSEER_BIND_HOST}:${MESHSEER_BIND_PORT}"
exec uv run meshseer
