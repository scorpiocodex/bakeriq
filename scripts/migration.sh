#!/usr/bin/env bash
# scripts/migration.sh — generate a new alembic migration with autogenerate.
#
# Prompts for the migration message rather than passing it via env var,
# which would force users to remember the variable name. Plain interactive
# prompt with sensible validation.

set -euo pipefail
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/_lib.sh"

ensure_compose_running

header "Generating migration"

# Prompt for migration message
echo
printf "  ${C_YELLOW}?${C_RESET} ${C_BOLD}Short description of the change${C_RESET} ${C_DIM}(e.g. 'add product table'):${C_RESET} "
read -r message

if [[ -z "$message" ]]; then
  status_fail "Message cannot be empty"
  exit 1
fi

echo

# Run alembic — note we intentionally do NOT use run_with_spinner here
# because alembic's autogenerate output is informative ("Detected added
# column..." etc.) and worth showing to the user. They need to read it
# critically before applying — that's the point of autogenerate.
status_running "Running alembic revision --autogenerate"
echo

if docker compose exec -T api alembic revision --autogenerate -m "$message"; then
  echo
  status_ok "Migration generated"
  status_info "Review the file in backend/alembic/versions/ before applying"
  status_info "Apply with: ${C_BOLD}make migrate${C_RESET}"
  echo
else
  echo
  status_fail "Migration generation failed"
  echo
  exit 1
fi
