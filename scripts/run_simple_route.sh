#!/usr/bin/env bash
set -Eeo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${ROBOTCI_PYTHON:-python3}"

if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
  PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
fi

cd "$PROJECT_ROOT"
exec "$PYTHON_BIN" -m robotci.cli run \
  --runtime native \
  --config robotci.yaml \
  --scenario simple_route \
  "$@"
