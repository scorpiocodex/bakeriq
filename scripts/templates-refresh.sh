#!/usr/bin/env bash
# scripts/templates-refresh.sh — re-bootstrap WhatsApp Content Templates.
#
# Use when:
#   - The templates have never been created (first-time setup)
#   - Templates were deleted on the Twilio side and need recreating
#
# What it does:
#   1. Verifies ngrok is running (otherwise bootstrap would bake an
#      empty/wrong URL)
#   2. Runs bootstrap_content_templates.py inside the api container. It
#      creates the templates that don't exist yet and reuses the SID of
#      every one that does (matched by name only; it never compares or
#      replaces an existing template's content)
#   3. Restarts api + worker so pydantic-settings re-reads backend/.env and
#      picks up any new CONTENT_SID_* values
#   4. Re-runs ngrok-check, which compares the tunnel with PUBLIC_BASE_URL
#      in .env
#
# It does NOT fix a template whose baked-in URL went stale after the ngrok
# hostname changed: that template already exists, so it is reused. For that,
# see docs/DEVELOPMENT.md ("The ngrok hostname problem").
#
# Idempotent; safe to run anytime.

set -euo pipefail
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/_lib.sh"

ensure_compose_running

header "Refreshing Content Templates"

# --- Step 1: ngrok sanity check ---------------------------------------------
# We don't reuse ngrok-check.sh wholesale because its exit-code-2 (drift)
# is actually fine here — drift is exactly what we're about to fix.
# We just need to confirm ngrok is up at all.
if ! pgrep -f "ngrok start" > /dev/null 2>&1; then
  status_fail "ngrok is not running"
  echo
  status_info "Bootstrap would bake an unreachable URL into the cart-link template."
  status_info "Start ngrok first:  ngrok start api &"
  status_info "Or run:             make dev-up"
  echo
  exit 1
fi

status_ok "ngrok process running"

# --- Step 2: run the bootstrap script ----------------------------------------
# This is the same script that runs during initial setup. It:
#   - Creates any of the 9 templates that don't exist on Twilio
#   - Reuses (does not recreate) the ones that do, even if their baked-in
#     URL is out of date
#   - Writes the resulting CONTENT_SID_* values to backend/.env
run_with_spinner "Running bootstrap_content_templates.py" \
  docker compose exec -T api python scripts/bootstrap_content_templates.py

# --- Step 3: restart api + worker so they re-read .env ----------------------
# pydantic-settings loads backend/.env at process start; updated SIDs from
# the bootstrap step won't be picked up until the processes restart.
run_with_spinner "Restarting api + worker (so .env is re-read)" \
  docker compose restart api worker

# Give the containers a few seconds to come back up before verifying
sleep 4

# --- Step 4: verify the new state matches ------------------------------------
# Re-run ngrok-check; we expect exit code 0 (no drift) after refresh.
# Suppress its output here and just check the exit code.
echo
status_running "Verifying templates point at the current tunnel"

if bash "$SCRIPT_DIR/ngrok-check.sh" > /dev/null 2>&1; then
  status_ok "Verified — templates aligned with current tunnel"
  echo
  status_info "Try sending a test message:  ${C_BOLD}make whatsapp-smoke${C_RESET}"
  echo
  exit 0
else
  status_fail "Verification failed — PUBLIC_BASE_URL still doesn't match the tunnel"
  echo
  status_info "Run for details:  ${C_BOLD}make ngrok-check${C_RESET}"
  status_info "Existing templates are reused, not replaced; see docs/DEVELOPMENT.md,"
  status_info "'The ngrok hostname problem'."
  echo
  exit 1
fi
