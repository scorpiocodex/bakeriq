#!/usr/bin/env bash
# scripts/test-fast.sh — pytest stop-at-first-failure mode.
#
# Useful when you've broken something and want to fix it before checking
# all the cascading failures. -x makes pytest exit as soon as one test fails.

set -euo pipefail
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/_lib.sh"

ensure_compose_running

header "Running tests (fail-fast)"
echo

set +e
docker compose exec -T api pytest tests/ -x -v
exit_status=$?
set -e

echo
if [[ $exit_status -eq 0 ]]; then
  status_ok "All tests passed"
else
  status_fail "Stopped at first failure (exit code $exit_status)"
fi
echo

exit $exit_status
