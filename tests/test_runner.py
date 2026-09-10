from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from robotci import runner
from robotci.config import PoseConfig, ScenarioConfig


def _make_project_root(path: Path) -> None:
    scripts = path / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (scripts / "run_navigation_scenario.sh").write_text(
        "#!/usr/bin/env bash\n",
        encoding="utf-8",
    )


def _write_config(path: Path, *, runtime: str = "native") -> Path:
    config_path = path / "robotci.yaml"
    config_path.write_text(
        f"""
version: 1
runtime: {runtime}
scenarios:
  - name: short_route
    start:
      x: 1.0
      y: 2.0
      yaw: 0.5
    goal:
      x: 4.0
      y: -0.17
      yaw: 0.25
    timeout_sec: 11
  - name: medium_route
    start:
      x: 0.0
      y: 0.0
    goal:
      x: 9.0
      y: -0.39
    timeout_sec: 22
  - name: simple_route
    start:
      x: 0.0
      y: 0.0
    goal:
      x: 17.86
      y: -0.77
    timeout_sec: 33
""".strip(),
        encoding="utf-8",
    )
    return config_path


def test_auto_runtime_prefers_native_ros_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner.stdlib_platform, "system", lambda: "Linux")
    monkeypatch.setattr(runner, "_command_exists", lambda command: command == "ros2")
    monkeypatch.setattr(runner, "_docker_available", lambda: True)

    assert runner.select_runtime("auto") == "native"


def test_auto_runtime_uses_docker_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner.stdlib_platform, "system", lambda: "Windows")
    monkeypatch.setattr(runner, "_docker_available", lambda: True)

    assert runner.select_runtime("auto") == "docker"


def test_auto_runtime_fails_cleanly_without_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner.stdlib_platform, "system", lambda: "Windows")
    monkeypatch.setattr(runner, "_docker_available", lambda: False)

    with pytest.raises(runner.RuntimeUnavailableError, match="no usable runtime found"):
        runner.select_runtime("auto")


def test_native_runtime_is_rejected_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner.stdlib_platform, "system", lambda: "Windows")

    with pytest.raises(runner.RuntimeUnavailableError, match="requires Linux"):
        runner.select_runtime("native")


def test_find_project_root_walks_up_from_nested_directory(tmp_path: Path) -> None:
    root = tmp_path / "robotci"
    nested = root / "some" / "nested" / "directory"
    nested.mkdir(parents=True)
    _make_project_root(root)

    assert runner._find_project_root(nested) == root


def test_run_native_passes_yaml_pose_and_timeout_to_script(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_project_root(tmp_path)
    script = tmp_path / "scripts" / "run_navigation_scenario.sh"
    output = tmp_path / ".robotci" / "result.json"
    captured: dict[str, object] = {}
    scenario = ScenarioConfig(
        name="custom_route",
        start=PoseConfig(x=1.0, y=2.0, yaw=0.5),
        goal=PoseConfig(x=4.0, y=-0.17, yaw=0.25),
        timeout_sec=42.5,
    )

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["cwd"] = kwargs["cwd"]
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    exit_code = runner._run_native(tmp_path, scenario, output, 42.5)

    assert exit_code == 0
    assert captured["command"] == ["bash", str(script)]
    assert captured["cwd"] == tmp_path
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert environment["ROBOTCI_SCENARIO"] == "custom_route"
    assert environment["ROBOTCI_START_X"] == "1.0"
    assert environment["ROBOTCI_START_Y"] == "2.0"
    assert environment["ROBOTCI_START_YAW"] == "0.5"
    assert environment["ROBOTCI_GOAL_X"] == "4.0"
    assert environment["ROBOTCI_GOAL_Y"] == "-0.17"
    assert environment["ROBOTCI_GOAL_YAW"] == "0.25"
    assert environment["ROBOTCI_RESULT_FILE"] == str(output.resolve())
    assert environment["ROBOTCI_TIMEOUT_SEC"] == "42.5"


def test_run_docker_mounts_config_and_copies_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_project_root(tmp_path)
    config_path = _write_config(tmp_path)
    source = tmp_path / "artifacts" / "short_route" / "result.json"
    destination = tmp_path / ".robotci" / "result.json"
    captured: dict[str, object] = {}
    scenario = ScenarioConfig(
        name="short_route",
        start=PoseConfig(x=1.0, y=2.0, yaw=0.5),
        goal=PoseConfig(x=4.0, y=-0.17, yaw=0.25),
        timeout_sec=30.0,
    )

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text('{"status": "PASS"}\n', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    exit_code = runner._run_docker(tmp_path, scenario, destination, 30.0, config_path)

    assert exit_code == 0
    assert destination.read_text(encoding="utf-8") == '{"status": "PASS"}\n'
    command = captured["command"]
    assert isinstance(command, list)
    assert command[:5] == ["docker", "compose", "run", "--rm", "--build"]
    assert "--volume" in command
    assert f"{config_path.resolve()}:/workspace/robotci.yaml:ro" in command
    assert "short_route" in command
    assert "30.0" in command


def test_read_result_status(tmp_path: Path) -> None:
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")

    assert runner.read_result_status(result_path) == "PASS"


def test_run_scenario_uses_yaml_runtime_pose_and_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_project_root(tmp_path)
    _write_config(tmp_path, runtime="native")
    captured: dict[str, object] = {}

    def fake_select_runtime(requested: str) -> str:
        captured["runtime"] = requested
        return "native"

    def fake_run_native(
        project_root: Path,
        scenario: ScenarioConfig,
        output: Path,
        timeout_sec: float,
    ) -> int:
        captured["scenario"] = scenario
        captured["timeout"] = timeout_sec
        return 0

    monkeypatch.setattr(runner, "select_runtime", fake_select_runtime)
    monkeypatch.setattr(runner, "_run_native", fake_run_native)

    exit_code, selected, _ = runner.run_scenario(
        scenario="short_route",
        project_root=tmp_path,
    )

    assert exit_code == 0
    assert selected == "native"
    assert captured["runtime"] == "native"
    scenario = captured["scenario"]
    assert isinstance(scenario, ScenarioConfig)
    assert scenario.start == PoseConfig(x=1.0, y=2.0, yaw=0.5)
    assert scenario.goal == PoseConfig(x=4.0, y=-0.17, yaw=0.25)
    assert captured["timeout"] == 11.0


def test_run_suite_uses_configured_scenarios_and_timeouts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_project_root(tmp_path)
    _write_config(tmp_path)
    monkeypatch.setattr(runner, "select_runtime", lambda requested: "native")
    executed: list[tuple[str, float]] = []

    def fake_run_native(
        project_root: Path,
        scenario: ScenarioConfig,
        output: Path,
        timeout_sec: float,
    ) -> int:
        assert project_root == tmp_path
        executed.append((scenario.name, timeout_sec))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "scenario": scenario.name,
                    "status": "PASS",
                    "duration_sec": 1.5,
                }
            ),
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(runner, "_run_native", fake_run_native)

    exit_code, selected, result_path = runner.run_suite(
        output=tmp_path / "suite-result.json",
        project_root=tmp_path,
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert selected == "native"
    assert payload["status"] == "PASS"
    assert [item["scenario"] for item in payload["scenarios"]] == [
        "short_route",
        "medium_route",
        "simple_route",
    ]
    assert executed == [
        ("short_route", 11.0),
        ("medium_route", 22.0),
        ("simple_route", 33.0),
    ]


def test_run_suite_cli_timeout_overrides_yaml_timeouts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_project_root(tmp_path)
    _write_config(tmp_path)
    monkeypatch.setattr(runner, "select_runtime", lambda requested: "native")
    observed_timeouts: list[float] = []

    def fake_run_native(
        project_root: Path,
        scenario: ScenarioConfig,
        output: Path,
        timeout_sec: float,
    ) -> int:
        observed_timeouts.append(timeout_sec)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps({"status": "PASS", "duration_sec": 1.0}),
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(runner, "_run_native", fake_run_native)

    runner.run_suite(
        timeout_sec=55.0,
        output=tmp_path / "suite-result.json",
        project_root=tmp_path,
    )

    assert observed_timeouts == [55.0, 55.0, 55.0]


def test_run_suite_propagates_worst_verdict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_project_root(tmp_path)
    _write_config(tmp_path)
    monkeypatch.setattr(runner, "select_runtime", lambda requested: "native")
    statuses = {
        "short_route": ("PASS", 0),
        "medium_route": ("FAIL", 1),
        "simple_route": ("TIMEOUT", 2),
    }

    def fake_run_native(
        project_root: Path,
        scenario: ScenarioConfig,
        output: Path,
        timeout_sec: float,
    ) -> int:
        status, exit_code = statuses[scenario.name]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps({"scenario": scenario.name, "status": status, "duration_sec": 1.0}),
            encoding="utf-8",
        )
        return exit_code

    monkeypatch.setattr(runner, "_run_native", fake_run_native)

    exit_code, _, result_path = runner.run_suite(
        output=tmp_path / "suite-result.json",
        project_root=tmp_path,
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert payload["status"] == "TIMEOUT"
