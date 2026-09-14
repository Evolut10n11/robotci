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
_RUNTIME_VARIABLE_NAMES = frozenset(
    {
        "AMENT_PREFIX_PATH",
        "BASH_ENV",
        "CMAKE_PREFIX_PATH",
        "COLCON_PREFIX_PATH",
        "HOME",
        "LANG",
        "LANGUAGE",
        "LD_LIBRARY_PATH",
        "PATH",
        "PYTHONPATH",
        "ROBOTCI_ATTEMPT_SCRIPT",
        "ROBOTCI_LOG_FILE",
        "ROBOTCI_RETRY_DELAY_SEC",
        "TMPDIR",
    }
)
_RUNTIME_VARIABLE_PREFIXES = (
    "CYCLONEDDS_",
    "FASTDDS_",
    "FASTRTPS_",
    "LC_",
    "RMW_",
    "ROS_",
    "ZENOH_",
)


class ReproducibilityError(ValueError):
    """Raised when suite execution provenance is missing, invalid, or unavailable."""


@dataclass(frozen=True)
class RuntimePackage:
    manager: PackageManager
    name: str
    version: str


@dataclass(frozen=True)
class RuntimeVariable:
    name: str
    value: str


@dataclass(frozen=True)
class RuntimeEnvironment:
    schema_version: int
    os_id: str
    os_version: str
    architecture: str
    python_version: str
    ros_distro: str
    robotci_build: str
    containerized: bool
    packages: tuple[RuntimePackage, ...]
    runtime_variables: tuple[RuntimeVariable, ...]
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


def _schema_version(value: object, *, expected: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value != expected:
        raise ReproducibilityError(f"{name} must be {expected}")


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
    robotci_build: str,
    containerized: bool,
    packages: Sequence[RuntimePackage],
    runtime_variables: Sequence[RuntimeVariable],
) -> dict[str, object]:
    return {
        "schema_version": ENVIRONMENT_SCHEMA_VERSION,
        "os_id": os_id,
        "os_version": os_version,
        "architecture": architecture,
        "python_version": python_version,
        "ros_distro": ros_distro,
        "robotci_build": robotci_build,
        "containerized": containerized,
        "packages": [asdict(package) for package in packages],
        "runtime_variables": [
            asdict(variable) for variable in runtime_variables
        ],
    }


def build_runtime_environment(
    *,
    os_id: str,
    os_version: str,
    architecture: str,
    python_version: str,
    ros_distro: str,
    robotci_build: str,
    containerized: bool,
    packages: Sequence[RuntimePackage],
    runtime_variables: Sequence[RuntimeVariable] = (),
) -> RuntimeEnvironment:
    values = {
        "os_id": os_id,
        "os_version": os_version,
        "architecture": architecture,
        "python_version": python_version,
        "ros_distro": ros_distro,
        "robotci_build": robotci_build,
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

    normalized_variables = tuple(
        sorted(runtime_variables, key=lambda item: item.name)
    )
    seen_variables: set[str] = set()
    for variable in normalized_variables:
        variable_name = _text(variable.name, "runtime_variable.name")
        if variable_name in seen_variables:
            raise ReproducibilityError(
                f"duplicate runtime variable: {variable_name}"
            )
        if not isinstance(variable.value, str):
            raise ReproducibilityError(
                f"runtime variable {variable_name!r} must have a string value"
            )
        seen_variables.add(variable_name)

    definition = _environment_definition(
        **normalized_values,
        containerized=containerized,
        packages=normalized_packages,
        runtime_variables=normalized_variables,
    )
    return RuntimeEnvironment(
        schema_version=ENVIRONMENT_SCHEMA_VERSION,
        **normalized_values,
        containerized=containerized,
        packages=normalized_packages,
        runtime_variables=normalized_variables,
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
            "robotci_build",
            "containerized",
            "packages",
            "runtime_variables",
            "fingerprint",
        },
        name=name,
    )
    _schema_version(
        payload.get("schema_version"),
        expected=ENVIRONMENT_SCHEMA_VERSION,
        name=f"{name}.schema_version",
    )

    raw_packages = payload.get("packages")
    if not isinstance(raw_packages, list | tuple):
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

    raw_variables = payload.get("runtime_variables")
    if not isinstance(raw_variables, list | tuple):
        raise ReproducibilityError(f"{name}.runtime_variables must be an array")
    runtime_variables: list[RuntimeVariable] = []
    for index, raw_variable in enumerate(raw_variables):
        variable_name = f"{name}.runtime_variables[{index}]"
        item = _mapping(raw_variable, variable_name)
        _reject_unknown_keys(
            item,
            allowed={"name", "value"},
            name=variable_name,
        )
        raw_value = item.get("value")
        if not isinstance(raw_value, str):
            raise ReproducibilityError(f"{variable_name}.value must be a string")
        runtime_variables.append(
            RuntimeVariable(
                name=_text(item.get("name"), f"{variable_name}.name"),
                value=raw_value,
            )
        )

    environment = build_runtime_environment(
        os_id=_text(payload.get("os_id"), f"{name}.os_id"),
        os_version=_text(payload.get("os_version"), f"{name}.os_version"),
        architecture=_text(payload.get("architecture"), f"{name}.architecture"),
        python_version=_text(payload.get("python_version"), f"{name}.python_version"),
        ros_distro=_text(payload.get("ros_distro"), f"{name}.ros_distro"),
        robotci_build=_fingerprint_text(
            payload.get("robotci_build"),
            f"{name}.robotci_build",
        ),
        containerized=payload.get("containerized"),
        packages=packages,
        runtime_variables=runtime_variables,
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


def build_robotci_source_fingerprint(
    package_root: Path | None = None,
    *,
    runtime_root: Path | None = None,
    attempt_script: Path | None = None,
    attempt_script_identity: str | None = None,
) -> str:
    """Hash the executable RobotCI Python and shell sources used by the runtime."""

    package = (package_root or Path(__file__).resolve().parent).resolve()
    runtime = (runtime_root or package.parent).resolve()
    sources = [
        (f"robotci/{path.relative_to(package).as_posix()}", path)
        for path in package.rglob("*.py")
    ]
    scripts = runtime / "scripts"
    if scripts.is_dir():
        sources.extend(
            (f"scripts/{path.relative_to(scripts).as_posix()}", path)
            for path in scripts.glob("*.sh")
        )
    selected_attempt_label: str | None = None
    if attempt_script is not None:
        lexical_attempt = attempt_script.absolute()
        selected_attempt = lexical_attempt.resolve()
        if not selected_attempt.is_file():
            raise ReproducibilityError(
                f"selected runtime attempt script does not exist: {selected_attempt}"
            )
        if attempt_script_identity is not None:
            if not isinstance(attempt_script_identity, str) or not attempt_script_identity:
                raise ReproducibilityError(
                    "attempt script identity must be a non-empty string"
                )
            selected_attempt_label = attempt_script_identity
        else:
            try:
                selected_attempt_label = (
                    "scripts/"
                    + lexical_attempt.relative_to(scripts.absolute()).as_posix()
                )
            except ValueError:
                selected_attempt_label = "selected-attempt-script"

        if selected_attempt not in {path.resolve() for _, path in sources}:
            try:
                source_label = (
                    "scripts/"
                    + selected_attempt.relative_to(scripts.resolve()).as_posix()
                )
            except ValueError:
                source_label = "selected-attempt-script"
            sources.append((source_label, selected_attempt))
    sources = sorted(sources, key=lambda item: item[0])
    if not sources:
        raise ReproducibilityError("RobotCI runtime source files are unavailable")

    files: list[dict[str, str]] = []
    for relative, path in sources:
        try:
            digest = sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise ReproducibilityError(
                f"cannot read RobotCI runtime source '{path}': {exc}"
            ) from exc
        files.append({"path": relative, "sha256": digest})
    return _fingerprint(
        {
            "files": files,
            "selected_attempt": selected_attempt_label,
        }
    )


def _resolve_attempt_script(runtime: Path) -> tuple[Path, str]:
    attempt_value = os.environ.get("ROBOTCI_ATTEMPT_SCRIPT", "")
    if attempt_value:
        attempt_script = Path(attempt_value)
        attempt_identity = f"environment:{attempt_value}"
    else:
        attempt_script = runtime / "scripts" / "run_navigation_attempt.sh"
        attempt_identity = "default:scripts/run_navigation_attempt.sh"
    if not attempt_script.is_absolute():
        attempt_script = runtime / attempt_script
    return attempt_script, attempt_identity


def _runtime_variables() -> tuple[RuntimeVariable, ...]:
    names = sorted(
        name
        for name in os.environ
        if name in _RUNTIME_VARIABLE_NAMES
        or name.startswith(_RUNTIME_VARIABLE_PREFIXES)
    )
    return tuple(
        RuntimeVariable(name=name, value=os.environ[name])
        for name in names
    )


def collect_runtime_environment(
    runtime_root: Path | None = None,
) -> RuntimeEnvironment:
    """Capture the actual process environment used to execute the Nav2 suite."""

    os_id, os_version = _read_os_release()
    runtime = (
        runtime_root or Path(__file__).resolve().parent.parent
    ).resolve()
    attempt_script, attempt_script_identity = _resolve_attempt_script(runtime)

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
        robotci_build=build_robotci_source_fingerprint(
            runtime_root=runtime,
            attempt_script=attempt_script,
            attempt_script_identity=attempt_script_identity,
        ),
        containerized=Path("/.dockerenv").exists()
        or Path("/run/.containerenv").exists(),
        packages=(*_installed_python_packages(), *_installed_debian_packages()),
        runtime_variables=_runtime_variables(),
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
    _schema_version(
        payload.get("schema_version"),
        expected=EXECUTION_SCHEMA_VERSION,
        name=f"{name}.schema_version",
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
    _schema_version(
        payload.get("schema_version"),
        expected=SUITE_RESULT_SCHEMA_VERSION,
        name=f"{name}.schema_version",
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


def _collect_docker_environment(
    runtime_root: Path,
    *,
    build_image: bool = False,
) -> RuntimeEnvironment:
    command = [
        "docker",
        "compose",
        "run",
        "--rm",
        "--no-deps",
    ]
    if build_image:
        command.append("--build")
    command.extend(
        [
            "robotci",
            "python",
            "-m",
            "robotci.reproducibility",
        ]
    )
    try:
        completed = subprocess.run(
            command,
            cwd=runtime_root,
            capture_output=True,
            text=True,
            timeout=300 if build_image else 60,
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
    build_docker_image: bool = False,
) -> SuiteExecutionIdentity:
    environment = (
        collect_runtime_environment(runtime_root)
        if runtime == "native"
        else _collect_docker_environment(
            runtime_root,
            build_image=build_docker_image,
        )
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
    payload = runtime_environment_payload(
        collect_runtime_environment(Path.cwd())
    )
    print(json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
