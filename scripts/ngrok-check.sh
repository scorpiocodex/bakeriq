#!/usr/bin/env bash
# scripts/ngrok-check.sh — check ngrok tunnel state + detect template URL drift.
#
# Read-only. Reports three things:
#   1. Is ngrok running locally?
#   2. What hostname is the current tunnel serving?
#   3. Does that hostname match PUBLIC_BASE_URL in .env?
#
# Step 3 compares against .env only. It never asks Twilio what URL a Content
# Template actually has baked in, so it can't see a template that is stale
# while .env is correct. See docs/DEVELOPMENT.md ("The ngrok hostname
# problem") for the recovery steps.
#
# Exit codes:
#   0 — ngrok healthy and its hostname matches PUBLIC_BASE_URL
#   2 — PUBLIC_BASE_URL is unset or differs from the tunnel hostname
#   3 — ngrok not running
#
# Non-zero exits let callers (scripts/dev-up.sh) react automatically;
# direct users see human-readable status either way.

set -euo pipefail
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/_lib.sh"

header "Checking ngrok tunnel"

# --- Step 1: is ngrok running? ------------------------------------------------
# pgrep returns 0 if found, 1 if not. We check by process name; if you
# rename the ngrok binary this won't catch it — extremely unlikely.
if ! pgrep -f "ngrok start" > /dev/null 2>&1; then
  status_fail "ngrok is not running"
  echo
  status_info "Start with:    ngrok start api &"
  status_info "Or run:        make dev-up   (starts the full stack including ngrok)"
  echo
  exit 3
fi

status_ok "ngrok process running"

# --- Step 2: what's the current tunnel hostname? ------------------------------
# ngrok exposes a local API at 127.0.0.1:4040. We query it for active
# tunnels and grep the public URL out of the JSON. No jq dependency.
current_url=$(curl -s --max-time 3 http://127.0.0.1:4040/api/tunnels 2>/dev/null \
  | grep -oE 'https://[^"]+\.ngrok-free\.dev' \
  | head -1 || true)

if [[ -z "$current_url" ]]; then
  status_fail "ngrok is running but no HTTPS tunnel found"
  echo
  status_info "Check the ngrok web UI at http://127.0.0.1:4040"
  status_info "ngrok config might be misconfigured. Try: ngrok config check"
  echo
  exit 3
fi

status_ok "Current tunnel: ${C_BOLD}${current_url}${C_RESET}"

# --- Step 3: does it match the baked URL? -------------------------------------
# We read PUBLIC_BASE_URL from .env — the value bootstrap_content_templates.py
# bakes into the templates it creates. If it differs from the live tunnel,
# templates created earlier probably point at a stale hostname and the
# "Open cart" button will 404. (We can't confirm that from here; see above.)
env_file="${SCRIPT_DIR}/../.env"
if [[ ! -f "$env_file" ]]; then
  status_fail ".env file not found at ${env_file}"
  echo
  status_info "Set up .env first: cp .env.example .env"
  echo
  exit 1
fi

baked_url=$(grep -E '^PUBLIC_BASE_URL=' "$env_file" 2>/dev/null \
  | head -1 \
  | cut -d'=' -f2- \
  | tr -d '"' \
  | tr -d "'" || true)

if [[ -z "$baked_url" ]]; then
  status_info "PUBLIC_BASE_URL is not set in .env"
  status_info "Templates haven't been bootstrapped yet — run: make templates-refresh"
  echo
  exit 2
fi

status_info "Baked URL in .env: ${baked_url}"

if [[ "$current_url" == "$baked_url" ]]; then
  echo
  status_ok "${C_BOLD}No drift — templates point at the current tunnel${C_RESET}"
  echo
  exit 0
fi

# --- Drift detected -----------------------------------------------------------
echo
status_fail "Drift detected — current tunnel ≠ baked URL"
echo
status_info "Current:  ${current_url}"
status_info "Baked:    ${baked_url}"
echo
status_info "Content Templates created under the old hostname still point at it,"
status_info "so tapping 'Open cart' in WhatsApp will probably hit a 404."
echo
status_info "make templates-refresh will NOT replace them (it reuses templates that"
status_info "already exist). Follow: docs/DEVELOPMENT.md, 'The ngrok hostname problem'."
echo
exit 2
