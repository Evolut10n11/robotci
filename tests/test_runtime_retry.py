from __future__ import annotations

import os
import signal
import subprocess
import time
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
  wait-for-term)
    trap 'printf "%s\n" TERM > "$ROBOTCI_TERM_MARKER"; exit 143' TERM
    while true; do
      sleep 0.1
    done
    ;;
  *)
    exit 99
    ;;
esac
""",
        encoding="utf-8",
    )


def _wrapper_environment(tmp_path: Path, *, mode: str) -> tuple[dict[str, str], Path, Path]:
    attempt = tmp_path / "fake-attempt.sh"
    counter = tmp_path / "attempt-count.txt"
    log_file = tmp_path / "nav2.log"
    term_marker = tmp_path / "term-marker.txt"
    _write_fake_attempt(attempt)

    environment = os.environ.copy()
    environment.update(
        {
            "ROBOTCI_ATTEMPT_SCRIPT": str(attempt),
            "ROBOTCI_ATTEMPT_COUNTER": str(counter),
            "ROBOTCI_FAKE_MODE": mode,
            "ROBOTCI_LOG_FILE": str(log_file),
            "ROBOTCI_RETRY_DELAY_SEC": "0",
            "ROBOTCI_TERM_MARKER": str(term_marker),
        }
    )
    return environment, counter, term_marker


def _run_wrapper(tmp_path: Path, *, mode: str) -> tuple[subprocess.CompletedProcess[str], int]:
    root = Path(__file__).resolve().parents[1]
    wrapper = root / "scripts" / "run_navigation_scenario.sh"
    environment, counter, _ = _wrapper_environment(tmp_path, mode=mode)

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


def test_runtime_forwards_term_to_active_attempt(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    wrapper = root / "scripts" / "run_navigation_scenario.sh"
    environment, counter, term_marker = _wrapper_environment(tmp_path, mode="wait-for-term")

    process = subprocess.Popen(
        ["bash", str(wrapper)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    try:
        deadline = time.monotonic() + 5
        while not counter.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert counter.exists(), "fake attempt did not start"

        process.send_signal(signal.SIGTERM)
        return_code = process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)

    assert return_code == 143
    assert term_marker.read_text(encoding="utf-8").strip() == "TERM"
