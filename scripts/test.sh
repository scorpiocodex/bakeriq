#!/usr/bin/env bash
# scripts/test.sh — run the pytest suite in the api container.
#
# Args passed through: ./scripts/test.sh tests/test_customers.py runs only
# that file. Useful for development iteration.
#
# We don't use run_with_spinner here because pytest's output (PASSED/FAILED
# per test, the final summary) is the whole point — silencing it would
# defeat the purpose. Just show colours where pytest already does.

set -euo pipefail
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source "$SCRIPT_DIR/_lib.sh"

ensure_compose_running

header "Running tests"

# Pass through any args after the make target. With Make this requires
# a slight ceremony (see Makefile MAKEFLAGS handling); for now, args are
# whatever pytest itself accepts.
PYTEST_ARGS="${PYTEST_ARGS:-tests/ -v}"

echo

# Run pytest. We wrap in a subshell so we can capture the exit code
# without `set -e` aborting the script before our summary runs.
set +e
docker compose exec -T api pytest $PYTEST_ARGS
exit_status=$?
set -e

echo
if [[ $exit_status -eq 0 ]]; then
  status_ok "All tests passed"
else
  status_fail "Some tests failed (exit code $exit_status)"
fi
echo

exit $exit_status
