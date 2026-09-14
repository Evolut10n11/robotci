from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from robotci import runner
from robotci.config import PoseConfig, ScenarioConfig
from robotci.replay import default_replay_path

_AUDITED_COMPOSE = """services:
  robotci:
    build:
      context: .
    image: robotci:dev
    init: true
    volumes:
      - ./artifacts:/workspace/artifacts
"""


def test_run_docker_copies_replay_next_to_requested_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (tmp_path / "compose.yaml").write_text(_AUDITED_COMPOSE, encoding="utf-8")
    (tmp_path / "scripts" / "run_navigation_scenario.sh").write_text(
        "#!/usr/bin/env bash\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text("version: 1\n", encoding="utf-8")

    source_result = tmp_path / "artifacts" / "short_route" / "result.json"
    source_replay = default_replay_path(source_result)
    destination = tmp_path / ".robotci" / "result.json"
    scenario = ScenarioConfig(
        name="short_route",
        start=PoseConfig(x=0.0, y=0.0, yaw=0.0),
        goal=PoseConfig(x=1.0, y=1.0, yaw=0.0),
        timeout_sec=30.0,
    )

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        source_result.parent.mkdir(parents=True, exist_ok=True)
        source_result.write_text('{"status":"PASS"}\n', encoding="utf-8")
        source_replay.write_text('{"schema_version":1}\n', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    exit_code = runner._run_docker(
        tmp_path,
        scenario,
        destination,
        30.0,
        config_path,
    )

    assert exit_code == 0
    assert destination.read_text(encoding="utf-8") == '{"status":"PASS"}\n'
    assert default_replay_path(destination).read_text(encoding="utf-8") == (
        '{"schema_version":1}\n'
    )
