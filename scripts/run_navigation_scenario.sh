#!/usr/bin/env bash
set -uo pipefail

SCENARIO="${ROBOTCI_SCENARIO:-simple_route}"
LOG_FILE="${ROBOTCI_LOG_FILE:-/tmp/nav2-${SCENARIO}.log}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ATTEMPT_SCRIPT="$SCRIPT_DIR/run_navigation_attempt.sh"

is_known_loopback_map_race() {
  [ -f "$LOG_FILE" ] \
    && grep -Fq "Received GetMap request but not in ACTIVE state, ignoring!" "$LOG_FILE" \
    && grep -Fq "OverflowError: cannot convert float infinity to integer" "$LOG_FILE"
}

for attempt in 1 2; do
  bash "$ATTEMPT_SCRIPT"
  status=$?

  if [ "$status" -ne 3 ]; then
    exit "$status"
  fi

  if [ "$attempt" -eq 2 ] || ! is_known_loopback_map_race; then
    exit "$status"
  fi

  echo "RobotCI runtime: recognized Nav2 Loopback empty-map startup race."
  echo "Retrying scenario $SCENARIO once after runtime cleanup..."
  sleep 1
done

exit 3
