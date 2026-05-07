#!/usr/bin/env bash
# scripts/seed.sh — re-run the seed without rebuilding the schema.
#
# Use this when you want to refresh the customer fixtures but the
# schema is fine. Faster than reset-db because it skips the migrations
# step.
#
# Strategy: delete all customers (and any other seeded entities later),
# then run the seed script. The admin user is preserved — the seed
# script's _seed_admin_user() function is idempotent (skips if user
# with the same email already exists), so we don't risk wiping the
# user we just logged in as.
#
# If you want a totally clean slate including users, use `make reset-db`
# instead.

set -euo pipefail
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/_lib.sh"

ensure_compose_running

header "Reseeding database"

confirm "This will DELETE existing customers and reseed. Continue?" || {
  echo
  status_info "Aborted — no changes made."
  echo
  exit 0
}

echo

# Clear customer-related tables. Order matters once we have FK
# relationships: child tables before parent tables. For now, just
# customers. We deliberately do NOT clear the users table here —
# that would log you out. Use `make reset-db` for that.
run_with_spinner "Clearing existing customers" \
  docker compose exec -T db psql -U bakeriq -d bakeriq -c \
  "DELETE FROM customers;"

run_with_spinner "Inserting 8 customers" \
  docker compose exec -T api python -m scripts.seed_phase_2_customers

customer_count=$(docker compose exec -T db psql -U bakeriq -d bakeriq -tAc \
  "SELECT count(*) FROM customers")

echo
echo "  ${C_GREEN}${C_BOLD}Done.${C_RESET}"
status_info "${customer_count} customers in the dev database"
status_info "Existing users preserved"
echo