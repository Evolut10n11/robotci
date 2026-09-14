from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="a POSIX bash runtime is required for runtime adapter test",
)
def test_run_navigation_scenario_honors_attempt_script_override(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    scenario_script = repository_root / "scripts" / "run_navigation_scenario.sh"
    adapter_script = tmp_path / "adapter.sh"
    capture_file = tmp_path / "adapter-env.txt"

    adapter_script.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' \
  "$ROBOTCI_SCENARIO" \
  "$ROBOTCI_START_X" \
  "$ROBOTCI_START_Y" \
  "$ROBOTCI_GOAL_X" \
  "$ROBOTCI_GOAL_Y" \
  "$ROBOTCI_RESULT_FILE" \
  "$ROBOTCI_TIMEOUT_SEC" \
  > "$ROBOTCI_ADAPTER_CAPTURE"
exit 0
""",
        encoding="utf-8",
    )

    environment = os.environ.copy()
    environment.update(
        {
            "ROBOTCI_ATTEMPT_SCRIPT": str(adapter_script),
            "ROBOTCI_ADAPTER_CAPTURE": str(capture_file),
            "ROBOTCI_SCENARIO": "external_route",
            "ROBOTCI_START_X": "1.25",
            "ROBOTCI_START_Y": "-2.5",
            "ROBOTCI_GOAL_X": "8.0",
            "ROBOTCI_GOAL_Y": "3.5",
            "ROBOTCI_RESULT_FILE": str(tmp_path / "result.json"),
            "ROBOTCI_TIMEOUT_SEC": "45",
        }
    )

    completed = subprocess.run(
        ["bash", str(scenario_script)],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert capture_file.read_text(encoding="utf-8").splitlines() == [
        "external_route",
        "1.25",
        "-2.5",
        "8.0",
        "3.5",
        str(tmp_path / "result.json"),
        "45",
    ]
