from __future__ import annotations

import json
import math
import os
import platform as stdlib_platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Literal, cast

from robotci.config import (
    ConfigError,
    PoseConfig,
    RuntimeName,
    ScenarioConfig,
    get_scenario,
    load_config,
)
from robotci.native_runtime import probe_native_ros
from robotci.project import DEFAULT_CONFIG_PATH, resolve_project_context
from robotci.replay import default_replay_path
from robotci.results import (
    RESULT_SCHEMA_VERSION,
    TASK_SCHEMA_VERSION,
    Pose2D,
    ScenarioStatus,
    SuiteResult,
    SuiteScenarioResult,
    build_scenario_task,
    write_suite_result,
)

DEFAULT_RESULT_PATH = Path(".robotci") / "result.json"
DEFAULT_SUITE_RESULT_PATH = Path(".robotci") / "suite-result.json"

_EXIT_BY_STATUS = {
    "PASS": 0,
    "FAIL": 1,
    "TIMEOUT": 2,
    "INFRA_ERROR": 3,
}
_STATUS_BY_EXIT = {code: status for status, code in _EXIT_BY_STATUS.items()}


class RuntimeUnavailableError(RuntimeError):
    """Raised when RobotCI cannot find a usable scenario runtime."""


def _command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def _docker_available() -> bool:
    if not _command_exists("docker"):
        return False

    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False

    return result.returncode == 0


def _native_ros_available() -> bool:
    if stdlib_platform.system() != "Linux":
        return False

    return probe_native_ros()


def select_runtime(requested: RuntimeName = "auto") -> Literal["native", "docker"]:
    if requested == "native":
        if not _native_ros_available():
            raise RuntimeUnavailableError(
                "native runtime requires Linux with ROS2 Jazzy/Nav2 installed"
            )
        return "native"

    if requested == "docker":
        if not _docker_available():
            raise RuntimeUnavailableError(
                "Docker runtime is unavailable; make sure Docker is installed "
                "and the daemon is running"
            )
        return "docker"

    if requested != "auto":
        raise ValueError(f"unsupported runtime: {requested}")

    if _native_ros_available():
        return "native"
    if _docker_available():
        return "docker"

    raise RuntimeUnavailableError(
        "no usable runtime found; install ROS2 Jazzy/Nav2 on Ubuntu or start Docker"
    )


def _find_runtime_root(start: Path | None = None) -> Path:
    """Find RobotCI-owned scripts and Compose files independently of user data."""

    candidates: list[Path] = []

    current = (start or Path.cwd()).resolve()
    candidates.extend((current, *current.parents))

    package_root = Path(__file__).resolve().parent.parent
    if package_root not in candidates:
        candidates.append(package_root)

    for candidate in candidates:
        if (candidate / "scripts" / "run_navigation_scenario.sh").is_file() and (
            candidate / "pyproject.toml"
        ).is_file():
            return candidate

    raise RuntimeUnavailableError(
        "RobotCI runtime assets were not found; install a complete RobotCI package "
        "or run from a RobotCI checkout"
    )


def _run_native(
    runtime_root: Path,
    scenario: ScenarioConfig,
    output: Path,
    timeout_sec: float,
) -> int:
    script = runtime_root / "scripts" / "run_navigation_scenario.sh"
    environment = os.environ.copy()
    half_yaw = scenario.start.yaw / 2.0

    environment.update(
        {
            "ROBOTCI_SCENARIO": scenario.name,
            "ROBOTCI_START_X": str(scenario.start.x),
            "ROBOTCI_START_Y": str(scenario.start.y),
            "ROBOTCI_START_YAW": str(scenario.start.yaw),
            "ROBOTCI_START_QZ": str(math.sin(half_yaw)),
            "ROBOTCI_START_QW": str(math.cos(half_yaw)),
            "ROBOTCI_GOAL_X": str(scenario.goal.x),
            "ROBOTCI_GOAL_Y": str(scenario.goal.y),
            "ROBOTCI_GOAL_YAW": str(scenario.goal.yaw),
            "ROBOTCI_MAP_ID": scenario.map_id or "unspecified",
            "ROBOTCI_RESULT_FILE": str(output.resolve()),
            "ROBOTCI_TIMEOUT_SEC": str(timeout_sec),
            "ROBOTCI_PYTHON": sys.executable,
        }
    )

    try:
        completed = subprocess.run(
            ["bash", str(script)],
            cwd=runtime_root,
            env=environment,
            check=False,
        )
    except OSError as exc:
        raise RuntimeUnavailableError(f"failed to start native runtime: {exc}") from exc

    return completed.returncode


def _run_docker(
    runtime_root: Path,
    scenario: ScenarioConfig,
    output: Path,
    timeout_sec: float,
    config_path: Path,
) -> int:
    container_result = f"/workspace/artifacts/{scenario.name}/result.json"
    host_result = runtime_root / "artifacts" / scenario.name / "result.json"
    host_replay = default_replay_path(host_result)
    _clear_result_artifacts(host_result)
    _clear_result_artifacts(output)
    config_mount = f"{config_path.resolve()}:/workspace/robotci.yaml:ro"

    command = [
        "docker",
        "compose",
        "run",
        "--rm",
        "--build",
        "--volume",
        config_mount,
        "robotci",
        "robotci",
        "run",
        "--runtime",
        "native",
        "--config",
        "/workspace/robotci.yaml",
        "--scenario",
        scenario.name,
        "--output",
        container_result,
        "--timeout-sec",
        str(timeout_sec),
    ]

    try:
        completed = subprocess.run(command, cwd=runtime_root, check=False)
    except OSError as exc:
        raise RuntimeUnavailableError(f"failed to start Docker runtime: {exc}") from exc

    resolved_output = output.resolve()
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    if host_result.is_file() and host_result.resolve() != resolved_output:
        shutil.copy2(host_result, resolved_output)

    if host_replay.is_file():
        replay_output = default_replay_path(resolved_output)
        replay_output.parent.mkdir(parents=True, exist_ok=True)
        if host_replay.resolve() != replay_output.resolve():
            shutil.copy2(host_replay, replay_output)

    return completed.returncode


def read_result_payload(path: str | Path) -> dict[str, object] | None:
    result_path = Path(path)
    if not result_path.is_file():
        return None

    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None

    return payload if isinstance(payload, dict) else None


def read_result_status(path: str | Path) -> str | None:
    payload = read_result_payload(path)
    if payload is None:
        return None

    status = payload.get("status")
    return status if isinstance(status, str) else None


def _clear_result_artifacts(path: Path) -> None:
    """Invalidate this attempt's result and replay before the runtime starts."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)
        default_replay_path(path).unlink(missing_ok=True)
    except OSError as exc:
        raise RuntimeUnavailableError(f"cannot prepare fresh result artifacts: {exc}") from exc


def _pose_matches(value: object, expected: PoseConfig) -> bool:
    if not isinstance(value, dict) or set(value) != {"x", "y", "yaw"}:
        return False
    for field in ("x", "y", "yaw"):
        coordinate = value[field]
        if isinstance(coordinate, bool) or not isinstance(coordinate, int | float):
            return False
        try:
            number = float(coordinate)
        except OverflowError:
            return False
        if not math.isfinite(number) or number != getattr(expected, field):
            return False
    return True


def _result_matches_task(payload: dict[str, object], scenario: ScenarioConfig) -> bool:
    task = payload.get("task")
    if not isinstance(task, dict) or set(task) != {
        "schema_version",
        "frame_id",
        "map_id",
        "fingerprint",
    }:
        return False
    task_version = task.get("schema_version")
    result_version = payload.get("schema_version")
    if (
        not isinstance(task_version, int)
        or isinstance(task_version, bool)
        or task_version != TASK_SCHEMA_VERSION
        or not isinstance(result_version, int)
        or isinstance(result_version, bool)
        or result_version != RESULT_SCHEMA_VERSION
    ):
        return False

    try:
        expected_task = build_scenario_task(
            scenario=scenario.name,
            start=Pose2D(scenario.start.x, scenario.start.y, scenario.start.yaw),
            goal=Pose2D(scenario.goal.x, scenario.goal.y, scenario.goal.yaw),
            map_id=scenario.map_id or "unspecified",
        )
    except (OverflowError, ValueError):
        return False
    return (
        _pose_matches(payload.get("start"), scenario.start)
        and _pose_matches(payload.get("goal"), scenario.goal)
        and task.get("frame_id") == expected_task.frame_id
        and task.get("map_id") == expected_task.map_id
        and task.get("fingerprint") == expected_task.fingerprint
    )


def _finalize_result(
    path: Path, scenario: ScenarioConfig, exit_code: int,
) -> tuple[int, ScenarioStatus, float]:
    """Keep process, scenario artifact and suite verdicts consistent, failing closed."""
    payload = read_result_payload(path)
    status = payload.get("status") if payload else None
    duration = payload.get("duration_sec") if payload else None
    valid_duration = (
        not isinstance(duration, bool)
        and isinstance(duration, int | float)
        and 0 <= duration <= sys.float_info.max
    )
    valid_status = isinstance(status, str) and status in _EXIT_BY_STATUS
    if (
        payload is not None
        and payload.get("scenario") == scenario.name
        and valid_status
        and valid_duration
        and _EXIT_BY_STATUS[status] == exit_code
        and _result_matches_task(payload, scenario)
    ):
        return exit_code, cast(ScenarioStatus, status), float(duration)

    # Do not preserve a misleading PASS on disk when the process failed, or a
    # malformed/foreign result when an adapter violated its result contract.
    error_payload = {
        "scenario": scenario.name,
        "status": "INFRA_ERROR",
        "duration_sec": 0.0,
        "runtime_exit_code": exit_code,
        "error": "missing, invalid or inconsistent runtime result",
    }
    try:
        default_replay_path(path).unlink(missing_ok=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(error_payload, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise RuntimeUnavailableError(f"cannot write runtime failure result: {exc}") from exc
    return 3, "INFRA_ERROR", 0.0


def run_scenario(
    *,
    scenario: str,
    runtime: RuntimeName | None = None,
    output: str | Path = DEFAULT_RESULT_PATH,
    timeout_sec: float | None = None,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    project_root: Path | None = None,
) -> tuple[int, Literal["native", "docker"], Path]:
    context = resolve_project_context(config_path, project_root=project_root)
    runtime_root = _find_runtime_root(context.project_root)
    config = load_config(context.config_path)
    definition = get_scenario(config, scenario)

    requested_runtime = runtime or config.runtime
    selected = select_runtime(requested_runtime)
    effective_timeout = definition.timeout_sec if timeout_sec is None else timeout_sec
    if effective_timeout <= 0:
        raise ConfigError("timeout must be greater than zero")

    result_path = Path(output)
    if not result_path.is_absolute():
        result_path = context.project_root / result_path
    result_path = result_path.resolve()
    _clear_result_artifacts(result_path)

    if selected == "native":
        exit_code = _run_native(runtime_root, definition, result_path, effective_timeout)
    else:
        exit_code = _run_docker(
            runtime_root,
            definition,
            result_path,
            effective_timeout,
            context.config_path,
        )

    exit_code, _, _ = _finalize_result(result_path, definition, exit_code)
    return exit_code, selected, result_path


def run_suite(
    *,
    runtime: RuntimeName | None = None,
    output: str | Path = DEFAULT_SUITE_RESULT_PATH,
    timeout_sec: float | None = None,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    project_root: Path | None = None,
) -> tuple[int, Literal["native", "docker"], Path]:
    context = resolve_project_context(config_path, project_root=project_root)
    runtime_root = _find_runtime_root(context.project_root)
    config = load_config(context.config_path)

    requested_runtime = runtime or config.runtime
    selected = select_runtime(requested_runtime)

    if timeout_sec is not None and timeout_sec <= 0:
        raise ConfigError("timeout must be greater than zero")

    suite_path = Path(output)
    if not suite_path.is_absolute():
        suite_path = context.project_root / suite_path
    suite_path = suite_path.resolve()
    try:
        suite_path.unlink(missing_ok=True)
    except OSError as exc:
        raise RuntimeUnavailableError(f"cannot prepare fresh suite result: {exc}") from exc

    scenario_dir = suite_path.parent / "results"
    started_at = time.monotonic()
    scenario_results: list[SuiteScenarioResult] = []
    final_exit_code = 0

    for definition in config.scenarios:
        result_path = scenario_dir / f"{definition.name}.json"
        effective_timeout = definition.timeout_sec if timeout_sec is None else timeout_sec
        _clear_result_artifacts(result_path)

        if selected == "native":
            exit_code = _run_native(
                runtime_root, definition, result_path, effective_timeout,
            )
        else:
            exit_code = _run_docker(
                runtime_root,
                definition,
                result_path,
                effective_timeout,
                context.config_path,
            )

        normalized_exit, status, duration = _finalize_result(
            result_path, definition, exit_code,
        )
        final_exit_code = max(final_exit_code, normalized_exit)
        scenario_results.append(
            SuiteScenarioResult(
                scenario=definition.name,
                status=cast(ScenarioStatus, status),
                duration_sec=float(duration),
                result_file=result_path.relative_to(suite_path.parent).as_posix(),
            )
        )

    suite_status = cast(ScenarioStatus, _STATUS_BY_EXIT[final_exit_code])
    suite = SuiteResult(
        status=suite_status,
        runtime=selected,
        duration_sec=round(time.monotonic() - started_at, 3),
        scenarios=tuple(scenario_results),
    )
    suite_path = write_suite_result(suite, suite_path)
    return final_exit_code, selected, suite_path
