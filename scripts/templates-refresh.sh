#!/usr/bin/env bash
# scripts/templates-refresh.sh — re-bootstrap WhatsApp Content Templates.
#
# Use when:
#   - `make ngrok-check` reports drift between current tunnel and baked URL
#   - You manually rotated the ngrok hostname
#   - You changed PUBLIC_BASE_URL in .env
#   - Templates were deleted on the Twilio side and need recreating
#
# What it does:
#   1. Verifies ngrok is running (otherwise bootstrap would bake an
#      empty/wrong URL)
#   2. Runs bootstrap_content_templates.py inside the api container —
#      this is idempotent; existing templates with the right shape are
#      left alone, mismatched ones recreated, missing ones created
#   3. Restarts api + worker so pydantic-settings re-reads .env and
#      picks up any updated CONTENT_SID_* values
#   4. Confirms the new state matches by re-running ngrok-check
#
# Idempotent; safe to run anytime, even if nothing has drifted.

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
#   - Creates any of the 4 templates that don't exist on Twilio
#   - Recreates the cart-link template if PUBLIC_BASE_URL has changed
#   - Writes the resulting CONTENT_SID_* values to .env
run_with_spinner "Running bootstrap_content_templates.py" \
  docker compose exec -T api python scripts/bootstrap_content_templates.py

# --- Step 3: restart api + worker so they re-read .env ----------------------
# pydantic-settings loads .env at process start; updated SIDs from the
# bootstrap step won't be picked up until the processes restart.
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
  status_fail "Verification failed — templates still appear drifted"
  echo
  status_info "Run for details:  ${C_BOLD}make ngrok-check${C_RESET}"
  echo
  exit 1
fi
