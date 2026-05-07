#!/usr/bin/env bash
# scripts/reset-db.sh — destructively rebuild the dev database.
#
# Steps:
#   1. Confirm with the user (they have 1 chance to back out)
#   2. Drop and recreate the public schema in the dev database
#   3. Run all alembic migrations from scratch
#   4. Run the seed Python script — admin user + 8 customers
#   5. Print a summary count
#
# Notes:
#   - Touches ONLY the dev database (bakeriq), not the test database (bakeriq_test)
#   - Uses public schema reset rather than DROP DATABASE because the latter
#     requires disconnecting clients first; schema reset is simpler and faster
#   - Seed script runs inside the api container (so it has access to models,
#     SQLAlchemy session config, settings — same as application code does)
#   - The admin user (owner@bakeriq.com / bakeriqowner) is re-seeded every
#     run because the schema drop wiped the users table along with everything
#     else. Without re-seeding, login breaks after every reset.

set -euo pipefail
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/_lib.sh"

ensure_compose_running

header "Resetting database"

confirm "This will DELETE all data in the dev database. Continue?" || {
  echo
  status_info "Aborted — no changes made."
  echo
  exit 0
}

echo

# --- Step 1: drop and recreate the public schema ------------------------------
# DROP SCHEMA public CASCADE removes every table, sequence, and type.
# CREATE SCHEMA public re-establishes the empty namespace.
run_with_spinner "Dropping all tables and types" \
  docker compose exec -T db psql -U bakeriq -d bakeriq -c \
  "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO bakeriq; GRANT ALL ON SCHEMA public TO public;"

# --- Step 2: run all migrations from scratch ----------------------------------
run_with_spinner "Running migrations" \
  docker compose exec -T api alembic upgrade head

# --- Step 3: run the seed script ----------------------------------------------
run_with_spinner "Seeding admin user and 8 customers" \
  docker compose exec -T api python -m scripts.seed_phase_2_customers

# --- Step 4: print summary ----------------------------------------------------
customer_count=$(docker compose exec -T db psql -U bakeriq -d bakeriq -tAc \
  "SELECT count(*) FROM customers")
user_count=$(docker compose exec -T db psql -U bakeriq -d bakeriq -tAc \
  "SELECT count(*) FROM users")

echo
echo "  ${C_GREEN}${C_BOLD}Done.${C_RESET}"
status_info "${user_count} user, ${customer_count} customers in the dev database"
status_info "Login: owner@bakeriq.com / bakeriqowner"
status_info "Products will be added in Phase 2 task 2"
echo