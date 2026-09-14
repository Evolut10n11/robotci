from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from pathlib import Path

import pytest

from robotci import runner
from robotci.config import PoseConfig, ScenarioConfig
from robotci.reproducibility import (
    RuntimePackage,
    build_runtime_environment,
    build_suite_execution_identity,
)
from robotci.results import Pose2D, build_scenario_task

_TEST_EXECUTION = build_suite_execution_identity(
    runtime="native",
    plan_fingerprint="sha256:" + "1" * 64,
    environment=build_runtime_environment(
        os_id="ubuntu",
        os_version="24.04",
        architecture="x86_64",
        python_version="3.12.3",
        ros_distro="jazzy",
        robotci_build="sha256:" + "2" * 64,
        containerized=False,
        packages=(RuntimePackage(manager="python", name="robotci", version="0.0.1"),),
    ),
)


@pytest.fixture(autouse=True)
def _stable_suite_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runner,
        "capture_suite_execution",
        lambda **kwargs: _TEST_EXECUTION,
    )


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
    map_id: warehouse-v1
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
    map_id: warehouse-v1
    start:
      x: 0.0
      y: 0.0
    goal:
      x: 9.0
      y: -0.39
    timeout_sec: 22
  - name: simple_route
    map_id: warehouse-v1
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


def _runtime_result_payload(
    scenario: ScenarioConfig,
    *,
    status: str = "PASS",
    duration_sec: float = 1.0,
    map_id: str | None = None,
) -> dict[str, object]:
    start = Pose2D(scenario.start.x, scenario.start.y, scenario.start.yaw)
    goal = Pose2D(scenario.goal.x, scenario.goal.y, scenario.goal.yaw)
    task_map_id = map_id or scenario.map_id or "unspecified"
    return {
        "schema_version": 2,
        "scenario": scenario.name,
        "status": status,
        "duration_sec": duration_sec,
        "navigation_result": "SUCCEEDED" if status == "PASS" else status,
        "start": asdict(start),
        "goal": asdict(goal),
        "metrics": {
            "path_length_m": 1.0,
            "distance_to_goal_m": 0.0,
            "stuck_events": 0,
            "feedback_samples": 1,
            "recoveries": 0,
        },
        "telemetry_quality": {
            "received_feedback_samples": 1,
            "valid_pose_samples": 1,
            "invalid_pose_samples": 0,
            "final_pose_valid": True,
        },
        "evidence_policy": {
            "goal_tolerance_m": scenario.goal_tolerance_m,
            "min_feedback_samples": scenario.min_feedback_samples,
        },
        **({"reason_code": status.lower()} if status != "PASS" else {}),
        "task": asdict(
            build_scenario_task(
                scenario=scenario.name,
                start=start,
                goal=goal,
                map_id=task_map_id,
            )
        ),
    }


def test_auto_runtime_prefers_native_ros_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner.stdlib_platform, "system", lambda: "Linux")
    monkeypatch.setattr(runner, "probe_native_ros", lambda: True)
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


def test_find_runtime_root_walks_up_from_nested_directory(tmp_path: Path) -> None:
    root = tmp_path / "robotci"
    nested = root / "some" / "nested" / "directory"
    nested.mkdir(parents=True)
    _make_project_root(root)

    assert runner._find_runtime_root(nested) == root


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
        map_id="warehouse-v1",
    )

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["cwd"] = kwargs["cwd"]
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setenv("BASH_ENV", str(tmp_path / "startup.sh"))
    monkeypatch.setenv("ENV", str(tmp_path / "posix-startup.sh"))
    monkeypatch.setenv("BASH_FUNC_injected%%", "() { return 0; }")
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
    assert environment["ROBOTCI_MAP_ID"] == "warehouse-v1"
    assert environment["ROBOTCI_RESULT_FILE"] == str(output.resolve())
    assert environment["ROBOTCI_TIMEOUT_SEC"] == "42.5"
    assert environment["ROBOTCI_GOAL_TOLERANCE_M"] == "0.25"
    assert environment["ROBOTCI_MIN_FEEDBACK_SAMPLES"] == "1"
    assert "BASH_ENV" not in environment
    assert "ENV" not in environment
    assert "BASH_FUNC_injected%%" not in environment


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
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(_runtime_result_payload(scenario)),
            encoding="utf-8",
        )
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


def test_run_scenario_rejects_adapter_pass_for_different_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_project_root(tmp_path)
    _write_config(tmp_path, runtime="native")
    monkeypatch.setattr(runner, "select_runtime", lambda requested: "native")

    def fake_run_native(
        project_root: Path,
        scenario: ScenarioConfig,
        output: Path,
        timeout_sec: float,
    ) -> int:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                _runtime_result_payload(scenario, map_id="different-warehouse")
            ),
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(runner, "_run_native", fake_run_native)

    exit_code, _, result_path = runner.run_scenario(
        scenario="short_route",
        project_root=tmp_path,
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert exit_code == 3
    assert payload["status"] == "INFRA_ERROR"
    assert payload["error"] == "missing, invalid or inconsistent runtime result"


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
            json.dumps(_runtime_result_payload(scenario, duration_sec=1.5)),
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
    assert payload["schema_version"] == 1
    assert payload["status"] == "PASS"
    assert payload["execution"]["fingerprint"] == _TEST_EXECUTION.fingerprint
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


def test_run_suite_rejects_runtime_environment_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_project_root(tmp_path)
    _write_config(tmp_path)
    monkeypatch.setattr(runner, "select_runtime", lambda requested: "native")
    drifted_execution = build_suite_execution_identity(
        runtime="native",
        plan_fingerprint=_TEST_EXECUTION.plan_fingerprint,
        environment=build_runtime_environment(
            os_id="ubuntu",
            os_version="24.04",
            architecture="x86_64",
            python_version="3.12.4",
            ros_distro="jazzy",
            robotci_build="sha256:" + "3" * 64,
            containerized=False,
            packages=(
                RuntimePackage(manager="python", name="robotci", version="0.0.1"),
            ),
        ),
    )
    captures = iter((_TEST_EXECUTION, drifted_execution))
    monkeypatch.setattr(
        runner,
        "capture_suite_execution",
        lambda **kwargs: next(captures),
    )

    def fake_run_native(
        project_root: Path,
        scenario: ScenarioConfig,
        output: Path,
        timeout_sec: float,
    ) -> int:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(_runtime_result_payload(scenario)),
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(runner, "_run_native", fake_run_native)
    suite_path = tmp_path / "suite-result.json"

    with pytest.raises(
        runner.RuntimeUnavailableError,
        match="runtime environment changed during suite execution",
    ):
        runner.run_suite(
            output=suite_path,
            project_root=tmp_path,
        )

    assert not suite_path.exists()


def test_run_suite_keeps_outputs_in_external_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    external_project = tmp_path / "pilot"
    external_project.mkdir()
    _write_config(external_project, runtime="native")
    monkeypatch.chdir(external_project)
    monkeypatch.setattr(runner, "select_runtime", lambda requested: "native")
    runtime_root = Path(runner.__file__).resolve().parent.parent
    observed_runtime_roots: list[Path] = []

    def fake_run_native(
        project_root: Path,
        scenario: ScenarioConfig,
        output: Path,
        timeout_sec: float,
    ) -> int:
        observed_runtime_roots.append(project_root)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                _runtime_result_payload(
                    scenario,
                    duration_sec=timeout_sec / 10,
                )
            ),
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(runner, "_run_native", fake_run_native)

    exit_code, selected, result_path = runner.run_suite()

    assert exit_code == 0
    assert selected == "native"
    assert result_path == (external_project / ".robotci" / "suite-result.json").resolve()
    assert observed_runtime_roots == [runtime_root, runtime_root, runtime_root]


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
            json.dumps(_runtime_result_payload(scenario)),
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
            json.dumps(
                _runtime_result_payload(scenario, status=status)
            ),
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
