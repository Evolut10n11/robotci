#!/usr/bin/env bash
set -uo pipefail

SCENARIO="${ROBOTCI_SCENARIO:-simple_route}"
LOG_FILE="${ROBOTCI_LOG_FILE:-/tmp/nav2-${SCENARIO}.log}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ATTEMPT_SCRIPT="${ROBOTCI_ATTEMPT_SCRIPT:-$SCRIPT_DIR/run_navigation_attempt.sh}"
RETRY_DELAY_SEC="${ROBOTCI_RETRY_DELAY_SEC:-1}"
ACTIVE_ATTEMPT_PID=""
RESULT_FILE="${ROBOTCI_RESULT_FILE:-artifacts/${SCENARIO}/result.json}"
PYTHON_BIN="${ROBOTCI_PYTHON:-python3}"
if [ -z "${ROBOTCI_PYTHON:-}" ] && [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi

clear_attempt_artifacts() {
  # Use the same helper and Python as the runtime; duplicating pathlib suffix
  # rules in Bash can leave stale replay files for unusual output names.
  "$PYTHON_BIN" -I -c '
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from robotci.replay import default_replay_path

result = Path(sys.argv[2])
for artifact in (result, default_replay_path(result), Path(sys.argv[3])):
    artifact.unlink(missing_ok=True)
' "$SCRIPT_DIR/.." "$RESULT_FILE" "$LOG_FILE"
}

terminate_active_attempt() {
  local signal="$1"
  local exit_code="$2"

  trap - TERM INT
  if [ -n "$ACTIVE_ATTEMPT_PID" ] && kill -0 "$ACTIVE_ATTEMPT_PID" 2>/dev/null; then
    kill "-$signal" "$ACTIVE_ATTEMPT_PID" 2>/dev/null || true
    wait "$ACTIVE_ATTEMPT_PID" 2>/dev/null || true
  fi
  exit "$exit_code"
}

trap 'terminate_active_attempt TERM 143' TERM
trap 'terminate_active_attempt INT 130' INT

is_known_loopback_map_race() {
  [ -f "$LOG_FILE" ] \
    && grep -Fq "Received GetMap request but not in ACTIVE state, ignoring!" "$LOG_FILE" \
    && grep -Fq "OverflowError: cannot convert float infinity to integer" "$LOG_FILE"
}

for attempt in 1 2; do
  # A retry is a new attempt: neither results nor race markers may survive it.
  if ! clear_attempt_artifacts; then
    echo "RobotCI runtime error: cannot clear previous attempt artifacts." >&2
    exit 3
  fi
  bash "$ATTEMPT_SCRIPT" &
  ACTIVE_ATTEMPT_PID=$!
  wait "$ACTIVE_ATTEMPT_PID"
  status=$?
  ACTIVE_ATTEMPT_PID=""

  if [ "$status" -ne 3 ]; then
    exit "$status"
  fi

  if [ "$attempt" -eq 2 ] || ! is_known_loopback_map_race; then
    exit "$status"
  fi

  echo "RobotCI runtime: recognized Nav2 Loopback empty-map startup race."
  echo "Retrying scenario $SCENARIO once after runtime cleanup..."
  sleep "$RETRY_DELAY_SEC"
done

exit 3
