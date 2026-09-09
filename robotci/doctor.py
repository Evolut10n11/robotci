from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    message: str


REQUIRED_ROS_PACKAGES = (
    "nav2_bringup",
    "nav2_loopback_sim",
    "nav2_simple_commander",
)


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


def run_doctor_checks() -> list[CheckResult]:
    results: list[CheckResult] = []

    ros2_available = command_exists("ros2")

    results.append(
        CheckResult(
            name="ros2",
            ok=ros2_available,
            message="ros2 command is available"
            if ros2_available
            else "ros2 command was not found",
        )
    )

    ros_distro = os.environ.get("ROS_DISTRO")

    results.append(
        CheckResult(
            name="ROS_DISTRO",
            ok=ros_distro == "jazzy",
            message=f"ROS_DISTRO={ros_distro}"
            if ros_distro
            else "ROS_DISTRO is not set",
        )
    )

    if not ros2_available:
        for package in REQUIRED_ROS_PACKAGES:
            results.append(
                CheckResult(
                    name=package,
                    ok=False,
                    message="cannot check package because ros2 is unavailable",
                )
            )

        return results

    for package in REQUIRED_ROS_PACKAGES:
        prefix = get_ros_package_prefix(package)

        results.append(
            CheckResult(
                name=package,
                ok=prefix is not None,
                message=f"installed at {prefix}"
                if prefix
                else "package was not found",
            )
        )

    return results