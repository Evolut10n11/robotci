from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass

from robotci.native_runtime import REQUIRED_ROS_PACKAGES
from robotci.platform import current_platform
from robotci.runner import RuntimeUnavailableError, select_runtime


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    message: str
    blocking: bool = True
    value: str | None = None


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def get_ros_package_prefix(package: str) -> str | None:
    try:
        result = subprocess.run(
            ["ros2", "pkg", "prefix", package],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        return None

    prefix = result.stdout.strip()
    return prefix or None


def get_docker_status() -> tuple[bool, str]:
    if not command_exists("docker"):
        return False, "docker command was not found"

    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "docker info timed out; the Docker daemon may not be running"
    except OSError as exc:
        return False, f"docker info failed: {exc}"

    if result.returncode != 0:
        return False, "docker command is available but the Docker daemon is not ready"

    return True, "docker daemon is available"


def _selected_runtime(*, strict_native_ros: bool) -> str:
    requested = "native" if strict_native_ros else "auto"
    try:
        return select_runtime(requested)
    except RuntimeUnavailableError:
        return "none"


def run_doctor_checks(*, require_ros: bool | None = None) -> list[CheckResult]:
    results: list[CheckResult] = []
    platform_info = current_platform()

    results.append(
        CheckResult(
            name="platform",
            ok=platform_info.core_supported,
            message=platform_info.summary,
        )
    )

    strict_native_ros = require_ros is True
    runtime_blocking = require_ros is not False
    ros2_available = command_exists("ros2")

    results.append(
        CheckResult(
            name="ros2",
            ok=ros2_available,
            message=(
                "ros2 command is available"
                if ros2_available
                else (
                    "ros2 command was not found; native ROS scenarios require "
                    "Linux with ROS2 Jazzy"
                )
            ),
            blocking=strict_native_ros,
        )
    )

    ros_distro = os.environ.get("ROS_DISTRO")
    results.append(
        CheckResult(
            name="ROS_DISTRO",
            ok=ros_distro == "jazzy",
            message=f"ROS_DISTRO={ros_distro}" if ros_distro else "ROS_DISTRO is not set",
            blocking=strict_native_ros,
        )
    )

    package_prefixes: dict[str, str | None] = {}
    for package in REQUIRED_ROS_PACKAGES:
        prefix = get_ros_package_prefix(package) if ros2_available else None
        package_prefixes[package] = prefix
        results.append(
            CheckResult(
                name=package,
                ok=prefix is not None,
                message=(
                    f"installed at {prefix}"
                    if prefix
                    else (
                        "package was not found"
                        if ros2_available
                        else "cannot check package because ros2 is unavailable"
                    )
                ),
                blocking=strict_native_ros,
            )
        )

    docker_ready, docker_message = get_docker_status()
    results.append(
        CheckResult(
            name="docker",
            ok=docker_ready,
            message=docker_message,
            blocking=False,
        )
    )

    native_ready = (
        platform_info.ros_runtime_supported
        and ros2_available
        and ros_distro == "jazzy"
        and all(prefix is not None for prefix in package_prefixes.values())
    )
    selected_runtime = _selected_runtime(strict_native_ros=strict_native_ros)

    if strict_native_ros:
        runtime_ready = native_ready
        runtime_message = (
            "native ROS2 Jazzy/Nav2 runtime is ready"
            if native_ready
            else "native ROS2 Jazzy/Nav2 runtime is incomplete"
        )
    elif selected_runtime == "native":
        runtime_ready = True
        runtime_message = "auto runtime will use native ROS2 Jazzy/Nav2"
    elif selected_runtime == "docker":
        runtime_ready = True
        runtime_message = "auto runtime will use Docker"
    else:
        runtime_ready = False
        runtime_message = (
            "no usable runtime found; install ROS2 Jazzy/Nav2 on Linux or start Docker"
        )

    results.append(
        CheckResult(
            name="runtime",
            ok=runtime_ready,
            message=runtime_message,
            blocking=runtime_blocking,
            value=selected_runtime,
        )
    )

    return results
