from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from robotci import runner
from robotci.replay import default_replay_path
from robotci.reproducibility import (
    RuntimePackage,
    build_runtime_environment,
    build_suite_execution_identity,
)
from robotci.result_schema import validate_result_payload
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


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/run_navigation_scenario.sh").touch()
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (tmp_path / "robotci.yaml").write_text(
        "version: 1\nruntime: native\nscenarios:\n"
        "  - name: route\n    start: {x: 0, y: 0}\n"
        "    goal: {x: 1, y: 0}\n    timeout_sec: 10\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "select_runtime", lambda requested: "native")
    monkeypatch.setattr(
        runner,
        "capture_suite_execution",
        lambda **kwargs: _TEST_EXECUTION,
    )
    return tmp_path


def _payload(status: str = "PASS") -> dict[str, object]:
    start = Pose2D(x=0.0, y=0.0, yaw=0.0)
    goal = Pose2D(x=1.0, y=0.0, yaw=0.0)
    return {
        "schema_version": 2,
        "scenario": "route",
        "status": status,
        "duration_sec": 1.5,
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
            "goal_tolerance_m": 0.25,
            "min_feedback_samples": 1,
        },
        **({"reason_code": status.lower()} if status != "PASS" else {}),
        "task": asdict(
            build_scenario_task(
                scenario="route",
                start=start,
                goal=goal,
                map_id="unspecified",
            )
        ),
    }


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _invoke(project: Path, mode: str) -> tuple[int, str, Path]:
    if mode == "single":
        return runner.run_scenario(
            scenario="route", output=project / "result.json", project_root=project,
        )
    return runner.run_suite(output=project / "suite.json", project_root=project)


def _scenario_path(project: Path, mode: str) -> Path:
    return project / ("result.json" if mode == "single" else "results/route.json")


@pytest.mark.parametrize("mode", ["single", "suite"])
@pytest.mark.parametrize("returncode", [0, 3, 127, -15])
def test_old_pass_cannot_satisfy_a_new_attempt(
    project: Path, monkeypatch: pytest.MonkeyPatch, mode: str, returncode: int,
) -> None:
    result = _scenario_path(project, mode)
    _write(result, _payload())
    default_replay_path(result).write_text("old replay", encoding="utf-8")
    _write(project / "suite.json", {"status": "PASS"})

    def no_result(root, scenario, output, timeout):
        assert not output.exists()
        assert not default_replay_path(output).exists()
        if mode == "suite":
            assert not (project / "suite.json").exists()
        return returncode

    monkeypatch.setattr(runner, "_run_native", no_result)
    code, _, output = _invoke(project, mode)
    assert code == 3
    assert runner.read_result_status(output) == "INFRA_ERROR"
    assert runner.read_result_status(result) == "INFRA_ERROR"
    assert not default_replay_path(result).exists()
    if mode == "suite":
        summary = runner.read_result_payload(output)
        assert summary["scenarios"][0]["status"] == "INFRA_ERROR"


@pytest.mark.parametrize("mode", ["single", "suite"])
@pytest.mark.parametrize("status,returncode", [("PASS", 3), ("PASS", 1), ("FAIL", 0),
                                              ("TIMEOUT", 127), ("PASS", -15)])
def test_conflicting_status_and_process_exit_fail_closed(
    project: Path, monkeypatch: pytest.MonkeyPatch, mode: str, status: str, returncode: int,
) -> None:
    def conflicting_result(root, scenario, output, timeout):
        _write(output, _payload(status))
        default_replay_path(output).write_text("misleading replay", encoding="utf-8")
        return returncode

    monkeypatch.setattr(runner, "_run_native", conflicting_result)
    code, _, output = _invoke(project, mode)
    assert code == 3
    assert runner.read_result_status(output) == "INFRA_ERROR"
    result = _scenario_path(project, mode)
    assert runner.read_result_status(result) == "INFRA_ERROR"
    assert not default_replay_path(result).exists()
    if mode == "suite":
        assert runner.read_result_payload(output)["scenarios"][0]["status"] == "INFRA_ERROR"


@pytest.mark.parametrize("mode", ["single", "suite"])
@pytest.mark.parametrize("status,returncode", [("PASS", 0), ("FAIL", 1),
                                              ("TIMEOUT", 2), ("INFRA_ERROR", 3)])
def test_fresh_consistent_verdicts_are_preserved(
    project: Path, monkeypatch: pytest.MonkeyPatch, mode: str, status: str, returncode: int,
) -> None:
    def valid_result(root, scenario, output, timeout):
        _write(output, _payload(status))
        default_replay_path(output).write_text("fresh replay", encoding="utf-8")
        return returncode

    monkeypatch.setattr(runner, "_run_native", valid_result)
    code, _, output = _invoke(project, mode)
    assert code == returncode
    assert runner.read_result_status(output) == status
    assert default_replay_path(_scenario_path(project, mode)).read_text() == "fresh replay"


@pytest.mark.parametrize("change", [
    {"scenario": "different_route"}, {"status": []}, {"duration_sec": float("nan")},
    {"duration_sec": float("inf")}, {"duration_sec": -1}, {"duration_sec": True},
    {"duration_sec": "1.5"}, {"duration_sec": 10**400},
    {"schema_version": 3},
])
def test_invalid_runtime_result_is_an_infrastructure_error(
    project: Path, monkeypatch: pytest.MonkeyPatch, change: dict[str, object],
) -> None:
    def invalid_result(root, scenario, output, timeout):
        _write(output, {**_payload(), **change})
        return 0

    monkeypatch.setattr(runner, "_run_native", invalid_result)
    code, _, path = _invoke(project, "single")
    assert code == 3
    assert runner.read_result_status(path) == "INFRA_ERROR"
    normalized = validate_result_payload(runner.read_result_payload(path))
    assert normalized.source_schema_version == 2
    assert normalized.metrics is None


def test_runtime_cannot_loosen_configured_evidence_policy(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def misleading_result(root, scenario, output, timeout):
        payload = _payload()
        policy = payload["evidence_policy"]
        assert isinstance(policy, dict)
        policy["goal_tolerance_m"] = 0.5
        metrics = payload["metrics"]
        assert isinstance(metrics, dict)
        metrics["distance_to_goal_m"] = 0.4
        _write(output, payload)
        return 0

    monkeypatch.setattr(runner, "_run_native", misleading_result)

    code, _, path = _invoke(project, "single")

    assert code == 3
    normalized = validate_result_payload(runner.read_result_payload(path))
    assert normalized.status == "INFRA_ERROR"
    assert normalized.reason_code == "runtime_result_invalid"


@pytest.mark.parametrize("contents", [b"not JSON", b"\xff\xfe", b"[]", b"null"])
def test_unreadable_result_is_normalized(
    project: Path, monkeypatch: pytest.MonkeyPatch, contents: bytes,
) -> None:
    def malformed_result(root, scenario, output, timeout):
        output.write_bytes(contents)
        return 0

    monkeypatch.setattr(runner, "_run_native", malformed_result)
    assert _invoke(project, "single")[0] == 3


def test_cannot_clear_old_artifact_stops_before_runtime(
    project: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = project / "result.json"
    result.mkdir()
    (result / "keep.txt").write_text("not a result", encoding="utf-8")
    monkeypatch.setattr(runner, "_run_native", lambda *args: pytest.fail("must not start"))
    with pytest.raises(runner.RuntimeUnavailableError, match="fresh result artifacts"):
        _invoke(project, "single")
    assert (result / "keep.txt").exists()


@pytest.mark.parametrize("returncode", [0, 3])
@pytest.mark.parametrize("same_output", [False, True])
def test_docker_cannot_copy_old_host_results_or_replays(
    project: Path, monkeypatch: pytest.MonkeyPatch, returncode: int, same_output: bool,
) -> None:
    monkeypatch.setattr(runner, "select_runtime", lambda requested: "docker")
    source = project / "artifacts/route/result.json"
    destination = source if same_output else project / "result.json"
    for path in (source, destination):
        _write(path, _payload())
        default_replay_path(path).write_text("stale", encoding="utf-8")

    def no_artifacts(command, **kwargs):
        assert not source.exists()
        assert not destination.exists()
        assert not default_replay_path(source).exists()
        assert not default_replay_path(destination).exists()
        return subprocess.CompletedProcess(command, returncode)

    monkeypatch.setattr(runner.subprocess, "run", no_artifacts)
    code, _, output = runner.run_scenario(
        scenario="route", output=destination, project_root=project,
    )
    assert code == 3
    assert runner.read_result_status(output) == "INFRA_ERROR"
    assert not default_replay_path(destination).exists()


@pytest.mark.parametrize("mode", ["single", "suite"])
def test_docker_still_publishes_fresh_result_and_replay(
    project: Path, monkeypatch: pytest.MonkeyPatch, mode: str,
) -> None:
    monkeypatch.setattr(runner, "select_runtime", lambda requested: "docker")
    source = project / "artifacts/route/result.json"

    def valid_container(command, **kwargs):
        _write(source, _payload())
        default_replay_path(source).write_text("fresh", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runner.subprocess, "run", valid_container)
    code, _, _ = _invoke(project, mode)
    assert code == 0
    assert default_replay_path(_scenario_path(project, mode)).read_text() == "fresh"


@pytest.mark.parametrize(
    "script_name",
    ["run_navigation_scenario.sh", "run_navigation_attempt.sh"],
)
def test_runtime_scripts_respect_explicit_python(script_name: str) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / script_name

    assert (
        'if [ -z "${ROBOTCI_PYTHON:-}" ] && [ -x ".venv/bin/python" ]; then'
        in script.read_text(encoding="utf-8")
    )


def test_runtime_python_disables_site_startup_and_bytecode_writes() -> None:
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    wrapper = (scripts / "run_navigation_scenario.sh").read_text(encoding="utf-8")
    attempt = (scripts / "run_navigation_attempt.sh").read_text(encoding="utf-8")

    assert '"$PYTHON_BIN" -S -B -c' in wrapper
    assert '"$PYTHON_BIN" -S -B -m robotci.ros.navigation_scenario' in attempt


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="POSIX shell")
def test_cleanup_python_ignores_sitecustomize_from_pythonpath(tmp_path: Path) -> None:
    wrapper = Path(__file__).resolve().parents[1] / "scripts/run_navigation_scenario.sh"
    adapter = tmp_path / "adapter.sh"
    marker = tmp_path / "sitecustomize-ran"
    (tmp_path / "sitecustomize.py").write_text(
        "import os\nfrom pathlib import Path\n"
        "Path(os.environ['STARTUP_MARKER']).write_text('ran', encoding='utf-8')\n",
        encoding="utf-8",
    )
    adapter.write_text("exit 0\n", encoding="utf-8")
    env = {
        **os.environ,
        "PYTHONPATH": str(tmp_path),
        "STARTUP_MARKER": str(marker),
        "ROBOTCI_ATTEMPT_SCRIPT": str(adapter),
        "ROBOTCI_PYTHON": sys.executable,
        "ROBOTCI_RESULT_FILE": str(tmp_path / "result.json"),
        "ROBOTCI_LOG_FILE": str(tmp_path / "nav2.log"),
    }

    completed = subprocess.run(
        ["bash", str(wrapper)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
    assert not marker.exists()


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="POSIX shell")
@pytest.mark.parametrize("filename", [
    "result.json", "result", ".result", ".result.json", "..json", "...json",
    "..x.json", "result.", "...", "with spaces.json", "result.json\n",
])
def test_shell_retry_clears_first_attempt_result_and_replay(
    tmp_path: Path, filename: str,
) -> None:
    wrapper = Path(__file__).resolve().parents[1] / "scripts/run_navigation_scenario.sh"
    adapter = tmp_path / "adapter.sh"
    result = tmp_path / filename
    replay = default_replay_path(result)
    counter = tmp_path / "attempt"
    log = tmp_path / "nav2.log"
    adapter.write_text(
        '''#!/usr/bin/env bash
if [ ! -f "$COUNT_FILE" ]; then
  touch "$COUNT_FILE"
  printf '{"status":"PASS"}' > "$ROBOTCI_RESULT_FILE"
  printf 'stale replay' > "$REPLAY_FILE"
  printf '%s\\n' 'Received GetMap request but not in ACTIVE state, ignoring!' \\
    'OverflowError: cannot convert float infinity to integer' > "$ROBOTCI_LOG_FILE"
  exit 3
fi
[ ! -e "$ROBOTCI_RESULT_FILE" ] || exit 91
[ ! -e "$REPLAY_FILE" ] || exit 92
exit 0
''', encoding="utf-8",
    )
    env = {**os.environ, "ROBOTCI_ATTEMPT_SCRIPT": str(adapter),
           "ROBOTCI_RESULT_FILE": str(result), "ROBOTCI_LOG_FILE": str(log),
           "REPLAY_FILE": str(replay), "COUNT_FILE": str(counter),
           "ROBOTCI_RETRY_DELAY_SEC": "0", "ROBOTCI_PYTHON": sys.executable}
    completed = subprocess.run(
        ["bash", str(wrapper)], cwd=tmp_path, env=env, capture_output=True, timeout=10,
    )
    # The wrapper cleans per-attempt artifacts; the Python runner then rejects
    # this adapter's zero exit without an artifact (covered by the tests above).
    assert completed.returncode == 0, completed.stderr
    assert counter.exists()
    assert not result.exists()
    assert not replay.exists()


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="POSIX shell")
def test_wrapper_stops_when_cleanup_python_is_unavailable(tmp_path: Path) -> None:
    wrapper = Path(__file__).resolve().parents[1] / "scripts/run_navigation_scenario.sh"
    adapter = tmp_path / "adapter.sh"
    marker = tmp_path / "started"
    adapter.write_text('touch "$STARTED_FILE"\n', encoding="utf-8")
    env = {**os.environ, "ROBOTCI_ATTEMPT_SCRIPT": str(adapter),
           "ROBOTCI_PYTHON": str(tmp_path / "missing-python"),
           "ROBOTCI_RESULT_FILE": str(tmp_path / "result.json"),
           "ROBOTCI_LOG_FILE": str(tmp_path / "nav2.log"), "STARTED_FILE": str(marker)}
    completed = subprocess.run(
        ["bash", str(wrapper)], cwd=tmp_path, env=env, capture_output=True, timeout=10,
    )
    assert completed.returncode == 3
    assert not marker.exists()


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="POSIX shell")
def test_wrapper_respects_explicit_python_over_project_venv(tmp_path: Path) -> None:
    wrapper = Path(__file__).resolve().parents[1] / "scripts/run_navigation_scenario.sh"
    project_python = tmp_path / ".venv/bin/python"
    project_python.parent.mkdir(parents=True)
    project_python.write_text(
        '#!/usr/bin/env bash\ntouch "$PROJECT_PYTHON_USED"\n',
        encoding="utf-8",
    )
    project_python.chmod(0o755)
    adapter = tmp_path / "adapter.sh"
    adapter.write_text('touch "$ADAPTER_STARTED"\n', encoding="utf-8")
    project_python_used = tmp_path / "project-python-used"
    adapter_started = tmp_path / "adapter-started"
    env = {
        **os.environ,
        "ROBOTCI_ATTEMPT_SCRIPT": str(adapter),
        "ROBOTCI_PYTHON": str(tmp_path / "missing-python"),
        "ROBOTCI_RESULT_FILE": str(tmp_path / "result.json"),
        "ROBOTCI_LOG_FILE": str(tmp_path / "nav2.log"),
        "PROJECT_PYTHON_USED": str(project_python_used),
        "ADAPTER_STARTED": str(adapter_started),
    }

    completed = subprocess.run(
        ["bash", str(wrapper)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        timeout=10,
    )

    assert completed.returncode == 3
    assert not project_python_used.exists()
    assert not adapter_started.exists()


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="POSIX shell")
def test_stale_race_log_cannot_trigger_retry(tmp_path: Path) -> None:
    wrapper = Path(__file__).resolve().parents[1] / "scripts/run_navigation_scenario.sh"
    adapter = tmp_path / "adapter.sh"
    counter = tmp_path / "attempts"
    log = tmp_path / "nav2.log"
    log.write_text(
        "Received GetMap request but not in ACTIVE state, ignoring!\n"
        "OverflowError: cannot convert float infinity to integer\n", encoding="utf-8",
    )
    adapter.write_text('echo attempt >> "$COUNT_FILE"\nexit 3\n', encoding="utf-8")
    env = {**os.environ, "ROBOTCI_ATTEMPT_SCRIPT": str(adapter),
           "ROBOTCI_PYTHON": sys.executable, "COUNT_FILE": str(counter),
           "ROBOTCI_RESULT_FILE": str(tmp_path / "result.json"),
           "ROBOTCI_LOG_FILE": str(log), "ROBOTCI_RETRY_DELAY_SEC": "0"}
    completed = subprocess.run(
        ["bash", str(wrapper)], cwd=tmp_path, env=env, capture_output=True, timeout=10,
    )
    assert completed.returncode == 3
    assert counter.read_text(encoding="utf-8").splitlines() == ["attempt"]
