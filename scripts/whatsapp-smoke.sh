#!/usr/bin/env bash
# scripts/whatsapp-smoke.sh — one-shot end-to-end smoke test.
#
# Sends the bakeriq_nav Content Template (Reorder / New / Status buttons)
# to a configured phone number. Verifies the full outbound chain works:
#
#   Twilio credentials valid → CONTENT_SID_NAV resolved → template renders
#   on WhatsApp → buttons display.
#
# Costs ~1 message of your Twilio sandbox daily quota (default 50/day).
# Run sparingly. Useful after:
#   - Initial setup, to confirm everything's wired
#   - `make templates-refresh`, to verify the new SIDs work
#   - A long break (days), to make sure nothing rotted on the Twilio side
#
# The destination phone is required and has no default, so a fork can never
# message someone else's number by accident. Use your own number, in
# international format, and make sure it has joined your Twilio sandbox:
#   SMOKE_TEST_PHONE=+91XXXXXXXXXX make whatsapp-smoke

set -euo pipefail
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/_lib.sh"

ensure_compose_running

# --- Configuration -----------------------------------------------------------
# No default on purpose: this sends a real WhatsApp message.
if [[ -z "${SMOKE_TEST_PHONE:-}" ]]; then
  status_fail "SMOKE_TEST_PHONE is not set"
  echo
  status_info "Give it YOUR number in international format, e.g."
  status_info "  SMOKE_TEST_PHONE=+91XXXXXXXXXX make whatsapp-smoke"
  status_info "The number must have joined your Twilio WhatsApp sandbox."
  echo
  exit 2
fi

header "WhatsApp smoke test"

status_info "Target:  ${C_BOLD}${SMOKE_TEST_PHONE}${C_RESET}"
status_info "Template: bakeriq_nav (Reorder / New / Status buttons)"
status_info "Cost:    1 message of today's Twilio sandbox quota"
echo

confirm "Send smoke test message?" || {
  echo
  status_info "Aborted — no message sent."
  echo
  exit 0
}

echo

# --- Send via Python (uses the same Twilio client our app uses) -------------
# We send via Python rather than curl + Twilio REST API directly because:
#   - The Twilio SDK reads our .env naturally
#   - Errors surface as Python exceptions with helpful messages
#   - It exercises the same code path as send_template() would
#
# heredoc piped to python inside the api container; same approach as the
# bootstrap script.
status_running "Sending bakeriq_nav template"

set +e
output=$(docker compose exec -T api python <<PY
import sys
from app.core.config import settings
from app.core.twilio_client import get_twilio_client

phone = "${SMOKE_TEST_PHONE}"
to = phone if phone.startswith("whatsapp:") else f"whatsapp:{phone}"

if not settings.CONTENT_SID_NAV:
    print("ERROR: CONTENT_SID_NAV is not set in .env", file=sys.stderr)
    print("Run: make templates-refresh", file=sys.stderr)
    sys.exit(2)

try:
    twilio = get_twilio_client()
    msg = twilio.messages.create(
        from_=settings.TWILIO_WHATSAPP_FROM,
        to=to,
        content_sid=settings.CONTENT_SID_NAV,
    )
    print(f"sent sid={msg.sid}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(1)
PY
)
exit_status=$?
set -e

if [[ $exit_status -ne 0 ]]; then
  status_fail "Send failed"
  echo
  echo "  ${C_DIM}Output:${C_RESET}"
  echo "$output" | sed 's/^/    /'
  echo
  status_info "Common causes:"
  status_info "  - Twilio sandbox daily quota (50 msgs) exhausted — try tomorrow"
  status_info "  - Target phone hasn't joined your Twilio sandbox — check Twilio console"
  status_info "  - CONTENT_SID_NAV in .env doesn't exist on Twilio — run: make templates-refresh"
  status_info "  - Twilio credentials invalid — verify TWILIO_* in .env"
  echo
  exit $exit_status
fi

status_ok "$output"
echo
status_info "Check your phone — message should arrive within 5 seconds."
status_info "Expected: 'What would you like to do next?' with 3 tappable buttons."
echo
