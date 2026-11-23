#!/usr/bin/env bash
# scripts/dev-up.sh — bring the full bakeriq dev stack online.
#
# Three things happen, in order:
#   1. Docker compose stack up (idempotent — already-up services aren't restarted)
#   2. ngrok started if not already running (idempotent — checks pgrep first)
#   3. Hostname check — compares the live tunnel with PUBLIC_BASE_URL in .env
#      and, on a mismatch, runs templates-refresh
#
# Be aware of what step 3 can and can't do. templates-refresh creates the
# templates that are missing and reuses the ones that exist, so it fixes a
# first-time setup (PUBLIC_BASE_URL unset, nothing created yet) but NOT a
# template whose baked-in URL went stale after the ngrok hostname rotated.
# In that case the verification fails and this script says so; follow
# docs/DEVELOPMENT.md ("The ngrok hostname problem"). A static ngrok domain
# avoids the problem entirely.
#
# Run after a fresh machine boot, after `make dev-down`, or any time you
# want to bring everything back to a known-good state.

set -euo pipefail
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/_lib.sh"

header "Starting bakeriq dev stack"

# --- Step 1: Docker compose up -----------------------------------------------
# `up -d` is idempotent — already-running services stay running, only
# missing/stopped services are started. Network creation respects the
# pinning we set up in docker-compose.yml (`name: bakeriq`, `bakeriq0`
# bridge interface).
run_with_spinner "Bringing up Docker services" \
  docker compose up -d

# Give services a few seconds to pass their healthchecks before we
# try anything that depends on them
sleep 4

# --- Step 2: ensure ngrok is running -----------------------------------------
# Free-tier ngrok sessions can die after long idles. Check first, start
# only if needed. nohup + & detaches it so closing the shell doesn't kill
# the tunnel; log to /tmp so we can grep later if anything went wrong.
if pgrep -f "ngrok start" > /dev/null 2>&1; then
  status_ok "ngrok already running"
else
  status_running "Starting ngrok (background)"
  nohup ngrok start api > /tmp/ngrok-bakeriq.log 2>&1 &

  # Wait for ngrok to actually serve a tunnel — pgrep returns
  # immediately but the tunnel takes ~2s to come up. Poll the local API.
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if curl -s --max-time 1 http://127.0.0.1:4040/api/tunnels 2>/dev/null \
        | grep -q "https://"; then
      break
    fi
    sleep 1
  done

  if curl -s --max-time 2 http://127.0.0.1:4040/api/tunnels 2>/dev/null \
      | grep -q "https://"; then
    status_ok "ngrok started"
  else
    status_fail "ngrok started but no tunnel detected after 10s"
    status_info "Check the log:  tail /tmp/ngrok-bakeriq.log"
    exit 1
  fi
fi

# --- Step 3: check the tunnel hostname against PUBLIC_BASE_URL ----------------
# ngrok-check.sh exits 0 if the tunnel hostname equals PUBLIC_BASE_URL in
# .env, 2 if PUBLIC_BASE_URL is unset or differs, 3 if ngrok isn't
# reachable. We already handled 3 above.
#
# On exit 2, run templates-refresh. That succeeds when the cause was "never
# bootstrapped"; when the hostname simply rotated it can't repair existing
# templates, so the verification at the end fails and we report it.
echo
status_running "Checking template URL alignment"

set +e
bash "$SCRIPT_DIR/ngrok-check.sh" > /tmp/ngrok-check.out 2>&1
check_status=$?
set -e

case $check_status in
  0)
    status_ok "PUBLIC_BASE_URL matches the current tunnel"
    ;;
  2)
    status_fail "PUBLIC_BASE_URL is unset or doesn't match the tunnel"
    echo
    status_info "Running templates-refresh (creates missing templates only)..."
    echo
    if bash "$SCRIPT_DIR/templates-refresh.sh"; then
      status_ok "templates-refresh succeeded"
    else
      status_fail "Still not aligned — manual steps needed"
      status_info "See:  ${C_BOLD}make ngrok-check${C_RESET} for details, and"
      status_info "docs/DEVELOPMENT.md, 'The ngrok hostname problem'"
      exit 1
    fi
    ;;
  *)
    status_fail "ngrok-check failed (exit $check_status)"
    sed 's/^/    /' /tmp/ngrok-check.out
    exit 1
    ;;
esac

# --- All systems go ----------------------------------------------------------
echo
echo "  ${C_GREEN}${C_BOLD}Stack ready.${C_RESET}"
status_info "Frontend:        http://localhost:5173"
status_info "API docs:        http://localhost:8000/docs"
status_info "ngrok webhook:   $(grep -oE 'https://[^"]+\.ngrok-free\.dev' /tmp/ngrok-check.out | head -1)"
echo
status_info "Optional smoke test:  ${C_BOLD}make whatsapp-smoke${C_RESET}"
echo
