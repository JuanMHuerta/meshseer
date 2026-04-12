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

: "${MESHRADAR_BIND_HOST:=0.0.0.0}"
: "${MESHRADAR_BIND_PORT:=8000}"
: "${MESHRADAR_DB_PATH:=./data/meshradar.db}"

mkdir -p -- "$(dirname -- "$MESHRADAR_DB_PATH")"

if PRECHECK_OUTPUT=$(uv run python -m meshradar.startup \
  --host "$MESHRADAR_BIND_HOST" \
  --port "$MESHRADAR_BIND_PORT"); then
  :
else
  PRECHECK_STATUS=$?
  case "$PRECHECK_STATUS" in
    10)
      echo "Meshradar is already running at ${PRECHECK_OUTPUT%/api/health}/"
      exit 0
      ;;
    11)
      echo "Port ${MESHRADAR_BIND_PORT} is already in use on ${MESHRADAR_BIND_HOST}." >&2
      echo "Stop the existing process or run with MESHRADAR_BIND_PORT=<port> ./start.sh" >&2
      exit 1
      ;;
    *)
      [ -n "$PRECHECK_OUTPUT" ] && printf '%s\n' "$PRECHECK_OUTPUT" >&2
      exit "$PRECHECK_STATUS"
      ;;
  esac
fi

echo "Starting Meshradar on ${MESHRADAR_BIND_HOST}:${MESHRADAR_BIND_PORT}"
exec uv run meshradar
