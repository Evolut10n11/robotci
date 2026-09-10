from __future__ import annotations

import json
import os
import platform as stdlib_platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal

RuntimeName = Literal["auto", "native", "docker"]
SUPPORTED_SCENARIOS = ("simple_route",)
DEFAULT_RESULT_PATH = Path(".robotci") / "result.json"


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
                "Docker runtime is unavailable; make sure Docker is installed and the daemon is running"
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
        if (candidate / "scripts" / "run_simple_route.sh").is_file() and (
            candidate / "pyproject.toml"
        ).is_file():
            return candidate

    raise RuntimeUnavailableError(
        "RobotCI project files were not found; run the command from a RobotCI checkout"
    )


def _run_native(project_root: Path, output: Path, timeout_sec: float) -> int:
    script = project_root / "scripts" / "run_simple_route.sh"
    environment = os.environ.copy()
    environment["ROBOTCI_RESULT_FILE"] = str(output.resolve())
    environment["ROBOTCI_TIMEOUT_SEC"] = str(timeout_sec)
    environment["ROBOTCI_PYTHON"] = sys.executable

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


def _run_docker(project_root: Path, output: Path, timeout_sec: float) -> int:
    container_result = "/workspace/artifacts/simple-route/result.json"
    host_result = project_root / "artifacts" / "simple-route" / "result.json"
    host_result.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "docker",
        "compose",
        "run",
        "--rm",
        "--build",
        "-e",
        f"ROBOTCI_RESULT_FILE={container_result}",
        "-e",
        f"ROBOTCI_TIMEOUT_SEC={timeout_sec}",
        "robotci",
    ]

    try:
        completed = subprocess.run(command, cwd=project_root, check=False)
    except OSError as exc:
        raise RuntimeUnavailableError(f"failed to start Docker runtime: {exc}") from exc

    if host_result.is_file():
        output = output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        if host_result.resolve() != output:
            shutil.copy2(host_result, output)

    return completed.returncode


def read_result_status(path: str | Path) -> str | None:
    result_path = Path(path)
    if not result_path.is_file():
        return None

    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    status = payload.get("status")
    return status if isinstance(status, str) else None


def run_scenario(
    *,
    scenario: str = "simple_route",
    runtime: RuntimeName = "auto",
    output: str | Path = DEFAULT_RESULT_PATH,
    timeout_sec: float = 90.0,
    project_root: Path | None = None,
) -> tuple[int, Literal["native", "docker"]]:
    if scenario not in SUPPORTED_SCENARIOS:
        supported = ", ".join(SUPPORTED_SCENARIOS)
        raise ValueError(f"unsupported scenario '{scenario}'; supported: {supported}")
    if timeout_sec <= 0:
        raise ValueError("timeout must be greater than zero")

    selected = select_runtime(runtime)
    root = _find_project_root(project_root)
    result_path = Path(output)

    if not result_path.is_absolute():
        result_path = root / result_path

    if selected == "native":
        exit_code = _run_native(root, result_path, timeout_sec)
    else:
        exit_code = _run_docker(root, result_path, timeout_sec)

    return exit_code, selected
