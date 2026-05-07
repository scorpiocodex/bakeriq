#!/usr/bin/env bash
# scripts/shell-db.sh — psql shell into the dev database.
#
# Useful for: ad-hoc SELECT queries, checking schema state, debugging
# migration issues.

set -euo pipefail
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/_lib.sh"

ensure_compose_running

header "psql shell — dev database"
status_info "Type \\q to exit"
status_info "Useful: \\dt (tables), \\d <table> (describe table)"
echo

docker compose exec db psql -U bakeriq -d bakeriq
