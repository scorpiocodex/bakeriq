#!/usr/bin/env bash
# scripts/_lib.sh — shared output styling for BakeriQ make targets.
#
# Sourced by every script under scripts/. Provides:
#   - Colour codes (auto-disabled if NO_COLOR is set or stdout is not a TTY)
#   - Header() — coloured section header with verb
#   - status_running / status_ok / status_fail — indicator + message
#   - run_with_spinner() — runs a command silently with an animated spinner
#   - confirm() — yes/no prompt that defaults to no
#
# All output goes to stdout. Errors from underlying commands are captured
# and shown only on failure, so successful runs stay quiet and clean.

set -euo pipefail

# --- Colour setup -------------------------------------------------------------
# Disable colour if:
#   - NO_COLOR env var is set (https://no-color.org spec)
#   - stdout is not a TTY (piped to file, etc.)
if [[ -n "${NO_COLOR:-}" ]] || [[ ! -t 1 ]]; then
  C_RESET=""
  C_DIM=""
  C_BOLD=""
  C_CYAN=""
  C_GREEN=""
  C_YELLOW=""
  C_RED=""
  C_BLUE=""
  C_MAGENTA=""
else
  C_RESET=$'\033[0m'
  C_DIM=$'\033[2m'
  C_BOLD=$'\033[1m'
  C_CYAN=$'\033[36m'
  C_GREEN=$'\033[32m'
  C_YELLOW=$'\033[33m'
  C_RED=$'\033[31m'
  C_BLUE=$'\033[34m'
  C_MAGENTA=$'\033[35m'
fi

# --- Header — verb-form section header ----------------------------------------
# Usage: header "Resetting database"
# Output:
#   <blank line>
#   ▸ Resetting database
#   ────────────────────
header() {
  local title="$1"
  local rule
  # Generate a horizontal rule the same length as "▸ TITLE"
  # Using printf to avoid seq dependency
  rule=$(printf '─%.0s' $(seq 1 $((${#title} + 2))))
  echo
  echo "${C_BOLD}${C_CYAN}▸ ${title}${C_RESET}"
  echo "${C_DIM}${rule}${C_RESET}"
}

# --- Status indicators --------------------------------------------------------
# status_running "Doing X"   — prints "  … Doing X" (cyan, italic)
# status_ok "Doing X"        — prints "  ✓ Doing X" (green)
# status_fail "Doing X"      — prints "  ✗ Doing X" (red)
# status_info "Note about Y" — prints "  · Note about Y" (dim)

status_running() {
  echo "  ${C_CYAN}…${C_RESET} ${C_DIM}$1${C_RESET}"
}

status_ok() {
  echo "  ${C_GREEN}✓${C_RESET} $1"
}

status_fail() {
  echo "  ${C_RED}✗${C_RESET} ${C_BOLD}$1${C_RESET}"
}

status_info() {
  echo "  ${C_DIM}· $1${C_RESET}"
}

# --- run_with_spinner — silent command with progress spinner ------------------
# Usage: run_with_spinner "Running migrations" docker compose exec api alembic upgrade head
#
# - Prints status_running + spinner
# - Runs command, captures combined stdout/stderr to a temp file
# - On success: clears spinner line, prints status_ok
# - On failure: clears spinner line, prints status_fail, shows captured output
#
# Spinner uses Braille pattern characters that animate cleanly in any
# Unicode-capable terminal. Falls back gracefully if NO_COLOR is set.

run_with_spinner() {
  local label="$1"
  shift

  local tmpfile
  tmpfile=$(mktemp)

  # Run the command in the background
  ("$@" >"$tmpfile" 2>&1) &
  local pid=$!

  # Spinner frames — Braille dots, smooth animation
  local frames=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
  local frame_count=${#frames[@]}
  local i=0

  # Hide cursor during spinner (re-enabled on exit)
  if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
    tput civis 2>/dev/null || true
  fi

  # Spin while command runs
  while kill -0 "$pid" 2>/dev/null; do
    local frame="${frames[$((i % frame_count))]}"
    printf "\r  ${C_CYAN}%s${C_RESET} ${C_DIM}%s${C_RESET}" "$frame" "$label"
    sleep 0.08
    i=$((i + 1))
  done

  # Show cursor again
  if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
    tput cnorm 2>/dev/null || true
  fi

  # Get the command's exit status
  wait "$pid"
  local exit_status=$?

  # Clear the spinner line
  printf "\r%*s\r" 80 ""

  if [[ $exit_status -eq 0 ]]; then
    status_ok "$label"
    rm -f "$tmpfile"
    return 0
  else
    status_fail "$label"
    echo
    echo "${C_DIM}Output:${C_RESET}"
    sed 's/^/    /' "$tmpfile"
    rm -f "$tmpfile"
    return $exit_status
  fi
}

# --- confirm — yes/no prompt that defaults to NO ------------------------------
# Usage: confirm "Delete everything?" || exit 0
# Returns 0 if user typed "y" or "Y" + enter; 1 otherwise.
confirm() {
  local prompt="$1"
  local response
  echo
  printf "  ${C_YELLOW}?${C_RESET} ${C_BOLD}%s${C_RESET} ${C_DIM}[y/N]${C_RESET} " "$prompt"
  read -r response
  case "$response" in
    [yY]|[yY][eE][sS])
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

# --- die — print error and exit -----------------------------------------------
die() {
  echo "${C_RED}${C_BOLD}Error:${C_RESET} $1" >&2
  exit 1
}

# --- ensure_compose_running — verify required containers are up ---------------
# Some commands need the api or db container running. If they're not, print
# a helpful message and exit cleanly rather than crashing on the next command.

ensure_compose_running() {
  if ! docker compose ps --format json 2>/dev/null | grep -q '"State":"running"'; then
    status_fail "Docker containers are not running"
    echo
    echo "  ${C_DIM}Start them with:${C_RESET} ${C_BOLD}docker compose up -d${C_RESET}"
    echo
    exit 1
  fi
}
