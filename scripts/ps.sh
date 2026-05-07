#!/usr/bin/env bash
# scripts/ps.sh — show docker compose container status, formatted.
#
# Wraps `docker compose ps` with a nice header. The compose output itself
# is already tabular and reasonable, so we just present it.

set -euo pipefail
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/_lib.sh"

header "Container status"
echo

docker compose ps

echo
