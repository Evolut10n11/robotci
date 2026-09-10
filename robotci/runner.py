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
    RuntimeName,
    ScenarioConfig,
    get_scenario,
    load_config,
)
from robotci.results import (
    ScenarioStatus,
    SuiteResult,
    SuiteScenarioResult,
    write_suite_result,
)

DEFAULT_CONFIG_PATH = Path("robotci.yaml")
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

    return _command_exists("ros2") or Path("/opt/ros/jazzy/setup.bash").is_file()


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


def _find_project_root(start: Path | None = None) -> Path:
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
        "RobotCI project files were not found; run the command from a RobotCI checkout"
    )


def _resolve_config_path(project_root: Path, config_path: str | Path) -> Path:
    path = Path(config_path)
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()


def _run_native(
    project_root: Path,
    scenario: ScenarioConfig,
    output: Path,
    timeout_sec: float,
) -> int:
    script = project_root / "scripts" / "run_navigation_scenario.sh"
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
            "ROBOTCI_RESULT_FILE": str(output.resolve()),
            "ROBOTCI_TIMEOUT_SEC": str(timeout_sec),
            "ROBOTCI_PYTHON": sys.executable,
        }
    )

    try:
        completed = subprocess.run(
            ["bash", str(script)],
            cwd=project_root,
            env=environment,
            check=False,
        )
    except OSError as exc:
        raise RuntimeUnavailableError(f"failed to start native runtime: {exc}") from exc

    return completed.returncode


def _run_docker(
    project_root: Path,
    scenario: ScenarioConfig,
    output: Path,
    timeout_sec: float,
    config_path: Path,
) -> int:
    container_result = f"/workspace/artifacts/{scenario.name}/result.json"
    host_result = project_root / "artifacts" / scenario.name / "result.json"
    host_result.parent.mkdir(parents=True, exist_ok=True)
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
        completed = subprocess.run(command, cwd=project_root, check=False)
    except OSError as exc:
        raise RuntimeUnavailableError(f"failed to start Docker runtime: {exc}") from exc

    if host_result.is_file():
        resolved_output = output.resolve()
        resolved_output.parent.mkdir(parents=True, exist_ok=True)
        if host_result.resolve() != resolved_output:
            shutil.copy2(host_result, resolved_output)

    return completed.returncode


def read_result_payload(path: str | Path) -> dict[str, object] | None:
    result_path = Path(path)
    if not result_path.is_file():
        return None

    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    return payload if isinstance(payload, dict) else None


def read_result_status(path: str | Path) -> str | None:
    payload = read_result_payload(path)
    if payload is None:
        return None

    status = payload.get("status")
    return status if isinstance(status, str) else None


def run_scenario(
    *,
    scenario: str,
    runtime: RuntimeName | None = None,
    output: str | Path = DEFAULT_RESULT_PATH,
    timeout_sec: float | None = None,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    project_root: Path | None = None,
) -> tuple[int, Literal["native", "docker"], Path]:
    root = _find_project_root(project_root)
    resolved_config = _resolve_config_path(root, config_path)
    config = load_config(resolved_config)
    definition = get_scenario(config, scenario)

    requested_runtime = runtime or config.runtime
    selected = select_runtime(requested_runtime)
    effective_timeout = definition.timeout_sec if timeout_sec is None else timeout_sec
    if effective_timeout <= 0:
        raise ConfigError("timeout must be greater than zero")

    result_path = Path(output)
    if not result_path.is_absolute():
        result_path = root / result_path
    result_path = result_path.resolve()

    if selected == "native":
        exit_code = _run_native(root, definition, result_path, effective_timeout)
    else:
        exit_code = _run_docker(
            root,
            definition,
            result_path,
            effective_timeout,
            resolved_config,
        )

    return exit_code, selected, result_path


def run_suite(
    *,
    runtime: RuntimeName | None = None,
    output: str | Path = DEFAULT_SUITE_RESULT_PATH,
    timeout_sec: float | None = None,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    project_root: Path | None = None,
) -> tuple[int, Literal["native", "docker"], Path]:
    root = _find_project_root(project_root)
    resolved_config = _resolve_config_path(root, config_path)
    config = load_config(resolved_config)

    requested_runtime = runtime or config.runtime
    selected = select_runtime(requested_runtime)

    if timeout_sec is not None and timeout_sec <= 0:
        raise ConfigError("timeout must be greater than zero")

    suite_path = Path(output)
    if not suite_path.is_absolute():
        suite_path = root / suite_path
    suite_path = suite_path.resolve()

    scenario_dir = suite_path.parent / "results"
    started_at = time.monotonic()
    scenario_results: list[SuiteScenarioResult] = []
    final_exit_code = 0

    for definition in config.scenarios:
        result_path = scenario_dir / f"{definition.name}.json"
        effective_timeout = definition.timeout_sec if timeout_sec is None else timeout_sec

        if selected == "native":
            exit_code = _run_native(root, definition, result_path, effective_timeout)
        else:
            exit_code = _run_docker(
                root,
                definition,
                result_path,
                effective_timeout,
                resolved_config,
            )

        payload = read_result_payload(result_path)
        status = payload.get("status") if payload is not None else None
        duration = payload.get("duration_sec") if payload is not None else None

        if status not in _EXIT_BY_STATUS:
            status = "INFRA_ERROR"
        if isinstance(duration, bool) or not isinstance(duration, int | float):
            duration = 0.0

        normalized_exit = exit_code if exit_code in _STATUS_BY_EXIT else 3
        final_exit_code = max(final_exit_code, _EXIT_BY_STATUS[status], normalized_exit)
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
