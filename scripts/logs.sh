#!/usr/bin/env bash
# scripts/logs.sh — tail api container logs.
#
# Just wraps `docker compose logs -f api` with a header. Press Ctrl+C
# to exit; that will return non-zero exit code from compose, which we
# trap and convert to a clean exit.

set -euo pipefail
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/_lib.sh"

ensure_compose_running

header "Tailing api logs"
status_info "Press Ctrl+C to exit"
echo

# Trap SIGINT (Ctrl+C) and exit cleanly rather than showing a traceback
trap 'echo; exit 0' SIGINT

docker compose logs -f api
