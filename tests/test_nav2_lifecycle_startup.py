from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


def _find_bash() -> str | None:
    if os.name == "nt":
        program_files = os.environ.get("ProgramFiles")
        if program_files:
            git_bash = Path(program_files) / "Git/bin/bash.exe"
            if git_bash.is_file():
                return str(git_bash)
        return None
    return shutil.which("bash")


BASH = _find_bash()
requires_bash = pytest.mark.skipif(
    BASH is None,
    reason="Nav2 lifecycle helper requires POSIX bash",
)


def _run_helper(tmp_path: Path, *, mode: str) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    helper = (
        Path(__file__).resolve().parents[1] / "scripts/nav2_lifecycle_startup.sh"
    )
    driver = tmp_path / "driver.sh"
    driver.write_text(
        r'''#!/usr/bin/env bash
set -u
source "$HELPER"

readiness_calls=0
startup_calls=0
sleep_calls=""

wait_for_service() {
  readiness_calls=$((readiness_calls + 1))
  [ "$MODE" != "readiness-transient" ] || [ "$readiness_calls" -gt 1 ]
}

call_startup() {
  startup_calls=$((startup_calls + 1))
  case "$MODE" in
    startup-transient)
      [ "$startup_calls" -gt 1 ]
      ;;
    exhausted)
      return 1
      ;;
    *)
      return 0
      ;;
  esac
}

sleep() {
  sleep_calls="${sleep_calls}${sleep_calls:+,}$1"
}

if start_lifecycle_with_retry /confirmed/manage_nodes "Navigation"; then
  status=0
else
  status=3
  echo "Navigation lifecycle startup failed"
fi

printf 'readiness=%s startup=%s sleeps=%s\n' \
  "$readiness_calls" "$startup_calls" "$sleep_calls"
exit "$status"
''',
        encoding="utf-8",
    )
    return subprocess.run(
        [BASH, str(driver)],
        capture_output=True,
        text=True,
        env={**os.environ, "HELPER": str(helper), "MODE": mode},
        check=False,
    )


@requires_bash
def test_lifecycle_service_ready_and_startup_succeeds_first_attempt(
    tmp_path: Path,
) -> None:
    completed = _run_helper(tmp_path, mode="ready")

    assert completed.returncode == 0
    assert "readiness=1 startup=1 sleeps=" in completed.stdout
    assert "attempt 1/3" in completed.stdout


@pytest.mark.parametrize(
    ("mode", "expected_counts"),
    [
        ("readiness-transient", "readiness=2 startup=1 sleeps=2"),
        ("startup-transient", "readiness=2 startup=2 sleeps=2"),
    ],
)
@requires_bash
def test_transient_lifecycle_readiness_or_startup_failure_is_retried(
    tmp_path: Path,
    mode: str,
    expected_counts: str,
) -> None:
    completed = _run_helper(tmp_path, mode=mode)

    assert completed.returncode == 0
    assert expected_counts in completed.stdout
    assert "Retrying Navigation lifecycle startup in 2 seconds" in completed.stdout


@requires_bash
def test_lifecycle_attempts_exhausted_preserves_infra_error(tmp_path: Path) -> None:
    completed = _run_helper(tmp_path, mode="exhausted")

    assert completed.returncode == 3
    assert "readiness=3 startup=3 sleeps=2,2" in completed.stdout
    assert "Navigation lifecycle startup exhausted after 3 attempts" in completed.stdout
    assert "Navigation lifecycle startup failed" in completed.stdout


def test_attempt_uses_confirmed_nav2_lifecycle_manager_services() -> None:
    attempt = (
        Path(__file__).resolve().parents[1] / "scripts/run_navigation_attempt.sh"
    ).read_text(encoding="utf-8")

    assert (
        'start_lifecycle_with_retry /lifecycle_manager_map_server/manage_nodes '
        '"Map server"' in attempt
    )
    assert (
        'start_lifecycle_with_retry /lifecycle_manager_navigation/manage_nodes '
        '"Navigation"' in attempt
    )
