#!/usr/bin/env bash
# scripts/shell-api.sh — drop into a bash shell inside the api container.
#
# Useful for: running one-off Python scripts, inspecting installed
# packages, debugging import paths.

set -euo pipefail
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/_lib.sh"

ensure_compose_running

header "Shell in api container"
status_info "Type 'exit' or Ctrl+D to leave"
echo

docker compose exec api bash
