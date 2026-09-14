from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from hashlib import sha256
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from pathlib import Path
from typing import Literal, cast

from robotci.config import RobotCIConfig

SUITE_RESULT_SCHEMA_VERSION = 1
ENVIRONMENT_SCHEMA_VERSION = 1
EXECUTION_SCHEMA_VERSION = 1
RUNTIME_CONTRACT = "ros2-nav2-jazzy-loopback-v1"

ExecutionRuntime = Literal["native", "docker"]
PackageManager = Literal["python", "deb"]

_PYTHON_DISTRIBUTIONS = ("robotci", "PyYAML", "rich", "typer")
_DEBIAN_PACKAGES = (
    "ros-jazzy-ros-base",
    "ros-jazzy-navigation2",
    "ros-jazzy-nav2-bringup",
    "ros-jazzy-nav2-loopback-sim",
    "ros-jazzy-nav2-simple-commander",
    "ros-jazzy-nav2-minimal-tb4-description",
)
_FINGERPRINT_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ReproducibilityError(ValueError):
    """Raised when suite execution provenance is missing, invalid, or unavailable."""


@dataclass(frozen=True)
class RuntimePackage:
    manager: PackageManager
    name: str
    version: str


@dataclass(frozen=True)
class RuntimeEnvironment:
    schema_version: int
    os_id: str
    os_version: str
    architecture: str
    python_version: str
    ros_distro: str
    containerized: bool
    packages: tuple[RuntimePackage, ...]
    fingerprint: str


@dataclass(frozen=True)
class SuiteExecutionIdentity:
    schema_version: int
    runtime: ExecutionRuntime
    runtime_contract: str
    plan_fingerprint: str
    environment: RuntimeEnvironment
    fingerprint: str


def _fingerprint(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(
        payload,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(canonical).hexdigest()}"


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ReproducibilityError(f"{name} must be a non-empty trimmed string")
    return value


def _fingerprint_text(value: object, name: str) -> str:
    text = _text(value, name)
    if not _FINGERPRINT_RE.fullmatch(text):
        raise ReproducibilityError(f"{name} must be a sha256 fingerprint")
    return text


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ReproducibilityError(f"{name} must be an object")
    return cast(dict[str, object], value)


def _reject_unknown_keys(
    payload: Mapping[str, object],
    *,
    allowed: set[str],
    name: str,
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ReproducibilityError(f"{name} contains unknown keys: {', '.join(unknown)}")


def _environment_definition(
    *,
    os_id: str,
    os_version: str,
    architecture: str,
    python_version: str,
    ros_distro: str,
    containerized: bool,
    packages: Sequence[RuntimePackage],
) -> dict[str, object]:
    return {
        "schema_version": ENVIRONMENT_SCHEMA_VERSION,
        "os_id": os_id,
        "os_version": os_version,
        "architecture": architecture,
        "python_version": python_version,
        "ros_distro": ros_distro,
        "containerized": containerized,
        "packages": [asdict(package) for package in packages],
    }


def build_runtime_environment(
    *,
    os_id: str,
    os_version: str,
    architecture: str,
    python_version: str,
    ros_distro: str,
    containerized: bool,
    packages: Sequence[RuntimePackage],
) -> RuntimeEnvironment:
    values = {
        "os_id": os_id,
        "os_version": os_version,
        "architecture": architecture,
        "python_version": python_version,
        "ros_distro": ros_distro,
    }
    normalized_values = {name: _text(value, name) for name, value in values.items()}
    if not isinstance(containerized, bool):
        raise ReproducibilityError("containerized must be a boolean")

    normalized_packages = tuple(sorted(packages, key=lambda item: (item.manager, item.name)))
    if not normalized_packages:
        raise ReproducibilityError("runtime packages must not be empty")

    seen: set[tuple[str, str]] = set()
    for package in normalized_packages:
        if package.manager not in {"python", "deb"}:
            raise ReproducibilityError(f"unsupported package manager: {package.manager!r}")
        _text(package.name, "package.name")
        _text(package.version, "package.version")
        key = (package.manager, package.name)
        if key in seen:
            raise ReproducibilityError(
                f"duplicate runtime package: {package.manager}:{package.name}"
            )
        seen.add(key)

    definition = _environment_definition(
        **normalized_values,
        containerized=containerized,
        packages=normalized_packages,
    )
    return RuntimeEnvironment(
        schema_version=ENVIRONMENT_SCHEMA_VERSION,
        **normalized_values,
        containerized=containerized,
        packages=normalized_packages,
        fingerprint=_fingerprint(definition),
    )


def runtime_environment_payload(environment: RuntimeEnvironment) -> dict[str, object]:
    return cast(dict[str, object], asdict(environment))


def parse_runtime_environment(
    value: object,
    *,
    name: str = "runtime environment",
) -> RuntimeEnvironment:
    payload = _mapping(value, name)
    _reject_unknown_keys(
        payload,
        allowed={
            "schema_version",
            "os_id",
            "os_version",
            "architecture",
            "python_version",
            "ros_distro",
            "containerized",
            "packages",
            "fingerprint",
        },
        name=name,
    )
    if payload.get("schema_version") != ENVIRONMENT_SCHEMA_VERSION:
        raise ReproducibilityError(
            f"{name}.schema_version must be {ENVIRONMENT_SCHEMA_VERSION}"
        )

    raw_packages = payload.get("packages")
    if not isinstance(raw_packages, list):
        raise ReproducibilityError(f"{name}.packages must be an array")
    packages: list[RuntimePackage] = []
    for index, raw_package in enumerate(raw_packages):
        package_name = f"{name}.packages[{index}]"
        item = _mapping(raw_package, package_name)
        _reject_unknown_keys(
            item,
            allowed={"manager", "name", "version"},
            name=package_name,
        )
        manager = item.get("manager")
        if manager not in {"python", "deb"}:
            raise ReproducibilityError(
                f"{package_name}.manager must be 'python' or 'deb'"
            )
        packages.append(
            RuntimePackage(
                manager=cast(PackageManager, manager),
                name=_text(item.get("name"), f"{package_name}.name"),
                version=_text(item.get("version"), f"{package_name}.version"),
            )
        )

    environment = build_runtime_environment(
        os_id=_text(payload.get("os_id"), f"{name}.os_id"),
        os_version=_text(payload.get("os_version"), f"{name}.os_version"),
        architecture=_text(payload.get("architecture"), f"{name}.architecture"),
        python_version=_text(payload.get("python_version"), f"{name}.python_version"),
        ros_distro=_text(payload.get("ros_distro"), f"{name}.ros_distro"),
        containerized=payload.get("containerized"),
        packages=packages,
    )
    supplied = _fingerprint_text(payload.get("fingerprint"), f"{name}.fingerprint")
    if supplied != environment.fingerprint:
        raise ReproducibilityError(f"{name}.fingerprint does not match its contents")
    return environment


def _read_os_release(path: Path = Path("/etc/os-release")) -> tuple[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ReproducibilityError(f"cannot read runtime OS identity: {exc}") from exc

    values: dict[str, str] = {}
    for line in lines:
        if "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"')
    try:
        return values["ID"], values["VERSION_ID"]
    except KeyError as exc:
        raise ReproducibilityError("runtime OS identity is incomplete") from exc


def _installed_debian_packages() -> tuple[RuntimePackage, ...]:
    try:
        completed = subprocess.run(
            ["dpkg-query", "-W", *_DEBIAN_PACKAGES],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReproducibilityError(f"cannot inspect ROS package versions: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"exit {completed.returncode}"
        raise ReproducibilityError(f"cannot inspect ROS package versions: {detail}")

    found: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        fields = line.split(maxsplit=1)
        if len(fields) == 2:
            found[fields[0]] = fields[1]
    missing = [name for name in _DEBIAN_PACKAGES if name not in found]
    if missing:
        raise ReproducibilityError(
            "runtime is missing version metadata for: " + ", ".join(missing)
        )
    return tuple(
        RuntimePackage(manager="deb", name=name, version=found[name])
        for name in _DEBIAN_PACKAGES
    )


def _installed_python_packages() -> tuple[RuntimePackage, ...]:
    packages: list[RuntimePackage] = []
    for name in _PYTHON_DISTRIBUTIONS:
        try:
            package_version = distribution_version(name)
        except PackageNotFoundError as exc:
            raise ReproducibilityError(
                f"runtime is missing Python distribution metadata for {name}"
            ) from exc
        packages.append(
            RuntimePackage(manager="python", name=name, version=package_version)
        )
    return tuple(packages)


def collect_runtime_environment() -> RuntimeEnvironment:
    """Capture the actual process environment used to execute the Nav2 suite."""

    os_id, os_version = _read_os_release()
    ros_distro = os.environ.get("ROS_DISTRO", "")
    if not ros_distro and Path("/opt/ros/jazzy").is_dir():
        ros_distro = "jazzy"
    if ros_distro != "jazzy":
        raise ReproducibilityError(
            f"runtime ROS distribution must be jazzy, got {ros_distro or 'unset'}"
        )

    return build_runtime_environment(
        os_id=os_id,
        os_version=os_version,
        architecture=platform.machine(),
        python_version=platform.python_version(),
        ros_distro=ros_distro,
        containerized=Path("/.dockerenv").exists()
        or Path("/run/.containerenv").exists(),
        packages=(*_installed_python_packages(), *_installed_debian_packages()),
    )


def build_suite_plan_fingerprint(
    config: RobotCIConfig,
    *,
    timeout_sec: float | None,
) -> str:
    """Fingerprint every effective input that changes suite execution semantics."""

    scenarios: list[dict[str, object]] = []
    for scenario in config.scenarios:
        effective_timeout = scenario.timeout_sec if timeout_sec is None else timeout_sec

        def pose_payload(x: float, y: float, yaw: float) -> dict[str, float]:
            return {
                name: 0.0 if float(value) == 0 else float(value)
                for name, value in zip(("x", "y", "yaw"), (x, y, yaw), strict=True)
            }

        scenarios.append(
            {
                "name": scenario.name,
                "frame_id": "map",
                "map_id": scenario.map_id or "unspecified",
                "start": pose_payload(
                    scenario.start.x,
                    scenario.start.y,
                    scenario.start.yaw,
                ),
                "goal": pose_payload(
                    scenario.goal.x,
                    scenario.goal.y,
                    scenario.goal.yaw,
                ),
                "timeout_sec": float(effective_timeout),
                "evidence_policy": {
                    "goal_tolerance_m": float(scenario.goal_tolerance_m),
                    "min_feedback_samples": scenario.min_feedback_samples,
                },
            }
        )
    return _fingerprint(
        {
            "config_version": config.version,
            "scenarios": scenarios,
        }
    )


def build_suite_execution_identity(
    *,
    runtime: ExecutionRuntime,
    plan_fingerprint: str,
    environment: RuntimeEnvironment,
) -> SuiteExecutionIdentity:
    if runtime not in {"native", "docker"}:
        raise ReproducibilityError(f"unsupported execution runtime: {runtime!r}")
    plan = _fingerprint_text(plan_fingerprint, "plan_fingerprint")
    effective_runtime: ExecutionRuntime = (
        "docker" if environment.containerized else runtime
    )
    definition = {
        "schema_version": EXECUTION_SCHEMA_VERSION,
        "runtime": effective_runtime,
        "runtime_contract": RUNTIME_CONTRACT,
        "plan_fingerprint": plan,
        "environment_fingerprint": environment.fingerprint,
    }
    return SuiteExecutionIdentity(
        schema_version=EXECUTION_SCHEMA_VERSION,
        runtime=effective_runtime,
        runtime_contract=RUNTIME_CONTRACT,
        plan_fingerprint=plan,
        environment=environment,
        fingerprint=_fingerprint(definition),
    )


def parse_suite_execution(
    value: object,
    *,
    name: str = "suite.execution",
) -> SuiteExecutionIdentity:
    payload = _mapping(value, name)
    _reject_unknown_keys(
        payload,
        allowed={
            "schema_version",
            "runtime",
            "runtime_contract",
            "plan_fingerprint",
            "environment",
            "fingerprint",
        },
        name=name,
    )
    if payload.get("schema_version") != EXECUTION_SCHEMA_VERSION:
        raise ReproducibilityError(
            f"{name}.schema_version must be {EXECUTION_SCHEMA_VERSION}"
        )
    runtime = payload.get("runtime")
    if runtime not in {"native", "docker"}:
        raise ReproducibilityError(f"{name}.runtime must be 'native' or 'docker'")
    contract = _text(payload.get("runtime_contract"), f"{name}.runtime_contract")
    if contract != RUNTIME_CONTRACT:
        raise ReproducibilityError(
            f"{name}.runtime_contract must be {RUNTIME_CONTRACT!r}"
        )
    environment = parse_runtime_environment(
        payload.get("environment"),
        name=f"{name}.environment",
    )
    execution = build_suite_execution_identity(
        runtime=cast(ExecutionRuntime, runtime),
        plan_fingerprint=_fingerprint_text(
            payload.get("plan_fingerprint"),
            f"{name}.plan_fingerprint",
        ),
        environment=environment,
    )
    supplied = _fingerprint_text(payload.get("fingerprint"), f"{name}.fingerprint")
    if supplied != execution.fingerprint:
        raise ReproducibilityError(f"{name}.fingerprint does not match its contents")
    return execution


def validate_suite_execution(
    suite: object,
    *,
    name: str = "suite result",
) -> SuiteExecutionIdentity:
    payload = _mapping(suite, name)
    if payload.get("schema_version") != SUITE_RESULT_SCHEMA_VERSION:
        raise ReproducibilityError(
            f"{name}.schema_version must be {SUITE_RESULT_SCHEMA_VERSION}"
        )
    execution = parse_suite_execution(
        payload.get("execution"),
        name=f"{name}.execution",
    )
    if payload.get("runtime") != execution.runtime:
        raise ReproducibilityError(
            f"{name}.runtime must match {name}.execution.runtime"
        )
    return execution


def _collect_docker_environment(runtime_root: Path) -> RuntimeEnvironment:
    command = [
        "docker",
        "compose",
        "run",
        "--rm",
        "--no-deps",
        "robotci",
        "python",
        "-m",
        "robotci.reproducibility",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=runtime_root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReproducibilityError(
            f"cannot capture Docker runtime environment: {exc}"
        ) from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"exit {completed.returncode}"
        raise ReproducibilityError(
            f"cannot capture Docker runtime environment: {detail}"
        )
    try:
        payload = json.loads(completed.stdout.strip())
    except json.JSONDecodeError as exc:
        raise ReproducibilityError(
            "Docker runtime returned invalid environment metadata"
        ) from exc
    return parse_runtime_environment(payload, name="Docker runtime environment")


def capture_suite_execution(
    *,
    config: RobotCIConfig,
    timeout_sec: float | None,
    runtime: ExecutionRuntime,
    runtime_root: Path,
) -> SuiteExecutionIdentity:
    environment = (
        collect_runtime_environment()
        if runtime == "native"
        else _collect_docker_environment(runtime_root)
    )
    return build_suite_execution_identity(
        runtime=runtime,
        plan_fingerprint=build_suite_plan_fingerprint(
            config,
            timeout_sec=timeout_sec,
        ),
        environment=environment,
    )


def main() -> int:
    payload = runtime_environment_payload(collect_runtime_environment())
    print(json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
