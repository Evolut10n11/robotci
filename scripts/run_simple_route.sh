#!/usr/bin/env bash
set -Eeo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROBOTCI_SCENARIO=simple_route exec "$SCRIPT_DIR/run_navigation_scenario.sh"
