#!/usr/bin/env bash
# scripts/help.sh — list available make targets, grouped by purpose.
#
# Output is hand-formatted (vs auto-generated from Makefile comments)
# because we want grouping, descriptions, and example use cases — none of
# which fit cleanly into makefile annotations.

set -euo pipefail
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/_lib.sh"

echo
echo "${C_BOLD}${C_CYAN}BakeriQ ${C_RESET}${C_DIM}— development commands${C_RESET}"
echo "${C_DIM}────────────────────────────────${C_RESET}"
echo

print_group() {
  echo "${C_BOLD}${C_BLUE}$1${C_RESET}"
}

print_target() {
  local target="$1"
  local description="$2"
  printf "  ${C_GREEN}%-20s${C_RESET}${C_DIM}%s${C_RESET}\n" "$target" "$description"
}

print_group "Dev stack"
print_target "dev-up"            "Start everything (docker + ngrok) and check the tunnel hostname"
echo

print_group "Database"
print_target "reset-db"          "Wipe dev DB → migrate → seed (asks for confirmation)"
print_target "seed"              "Re-run seed data only (DB already exists)"
print_target "migrate"           "Apply pending Alembic migrations"
print_target "migration"         "Generate a new auto-detected migration (prompts for message)"
echo

print_group "Tests"
print_target "test"              "Run full pytest suite (verbose)"
print_target "test-fast"         "Run pytest with -x (stop at first failure)"
echo

print_group "Containers"
print_target "ps"                "Show docker compose container status"
print_target "logs"              "Tail api container logs (Ctrl+C to exit)"
print_target "shell-api"         "Bash shell inside the api container"
print_target "shell-db"          "psql shell inside the dev database"
echo

print_group "WhatsApp / ngrok"
print_target "ngrok-check"       "Show ngrok hostname, flag template URL drift"
print_target "templates-refresh" "Re-bootstrap WhatsApp Content Templates (after ngrok rotation)"
print_target "whatsapp-smoke"    "Send one test nav-card to verify Twilio + templates end-to-end"
echo

echo "${C_DIM}Type ${C_RESET}${C_BOLD}make <target>${C_RESET}${C_DIM} to run.${C_RESET}"
echo
