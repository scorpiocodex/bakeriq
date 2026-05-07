#!/usr/bin/env bash
# scripts/migrate.sh — apply any pending Alembic migrations to the dev DB.
# Non-destructive; safe to run anytime.

set -euo pipefail
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/_lib.sh"

ensure_compose_running

header "Applying migrations"

# alembic upgrade head is idempotent — if no migrations are pending, it's a
# few-millisecond no-op. We don't need to check first.
run_with_spinner "Running alembic upgrade head" \
  docker compose exec -T api alembic upgrade head

# Show the current revision so we know where we ended up
echo
status_info "Current revision:"
docker compose exec -T api alembic current 2>&1 | sed 's/^/    /'
echo
