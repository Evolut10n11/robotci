from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="runtime wrapper requires bash")


def _write_fake_attempt(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env bash
set -u

count=0
if [ -f "$ROBOTCI_ATTEMPT_COUNTER" ]; then
  count="$(cat "$ROBOTCI_ATTEMPT_COUNTER")"
fi
count=$((count + 1))
printf '%s\n' "$count" > "$ROBOTCI_ATTEMPT_COUNTER"

case "$ROBOTCI_FAKE_MODE" in
  known-race)
    if [ "$count" -eq 1 ]; then
      cat > "$ROBOTCI_LOG_FILE" <<'EOF'
Received GetMap request but not in ACTIVE state, ignoring!
OverflowError: cannot convert float infinity to integer
EOF
      exit 3
    fi
    exit 0
    ;;
  infra-error)
    printf '%s\n' 'unrelated infrastructure failure' > "$ROBOTCI_LOG_FILE"
    exit 3
    ;;
  fail)
    exit 1
    ;;
  *)
    exit 99
    ;;
esac
""",
        encoding="utf-8",
    )


def _run_wrapper(tmp_path: Path, *, mode: str) -> tuple[subprocess.CompletedProcess[str], int]:
    root = Path(__file__).resolve().parents[1]
    wrapper = root / "scripts" / "run_navigation_scenario.sh"
    attempt = tmp_path / "fake-attempt.sh"
    counter = tmp_path / "attempt-count.txt"
    log_file = tmp_path / "nav2.log"
    _write_fake_attempt(attempt)

    environment = os.environ.copy()
    environment.update(
        {
            "ROBOTCI_ATTEMPT_SCRIPT": str(attempt),
            "ROBOTCI_ATTEMPT_COUNTER": str(counter),
            "ROBOTCI_FAKE_MODE": mode,
            "ROBOTCI_LOG_FILE": str(log_file),
            "ROBOTCI_RETRY_DELAY_SEC": "0",
        }
    )
    completed = subprocess.run(
        ["bash", str(wrapper)],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    return completed, int(counter.read_text(encoding="utf-8"))


def test_runtime_retries_known_loopback_empty_map_race_once(tmp_path: Path) -> None:
    completed, attempts = _run_wrapper(tmp_path, mode="known-race")

    assert completed.returncode == 0
    assert attempts == 2
    assert "recognized Nav2 Loopback empty-map startup race" in completed.stdout


def test_runtime_does_not_retry_unrelated_infra_error(tmp_path: Path) -> None:
    completed, attempts = _run_wrapper(tmp_path, mode="infra-error")

    assert completed.returncode == 3
    assert attempts == 1


def test_runtime_does_not_retry_robot_behavior_failure(tmp_path: Path) -> None:
    completed, attempts = _run_wrapper(tmp_path, mode="fail")

    assert completed.returncode == 1
    assert attempts == 1
