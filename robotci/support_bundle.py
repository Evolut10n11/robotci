from __future__ import annotations

import argparse
import json
import platform
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from robotci import __version__
from robotci.config import ConfigError, RuntimeName, load_config
from robotci.doctor import REQUIRED_ROS_PACKAGES, CheckResult, run_doctor_checks
from robotci.doctor_report import build_report

SCHEMA_VERSION = 1
_CONFIG_ERROR_MESSAGE = "RobotCI config is invalid; run 'robotci validate' locally for details"
_CONFIG_READ_ERROR_MESSAGE = (
    "RobotCI config could not be read; check file access locally and retry"
)
_PACKAGE_INSTALLED_MESSAGE = "package is installed"
# Messages in local doctor checks may contain environment values, OS error text,
# or paths. Share only controlled text, never the original diagnostic strings.
_CHECK_MESSAGES = {
    "platform": ("platform is not supported", "platform is supported"),
    "ros2": ("ros2 command is unavailable", "ros2 command is available"),
    "ROS_DISTRO": ("ROS2 Jazzy is not selected", "ROS2 Jazzy is selected"),
    "docker": ("Docker daemon is unavailable", "Docker daemon is available"),
    "runtime": ("runtime is not ready", "runtime is ready"),
}


def _config_report(config_path: Path) -> dict[str, object]:
    if not config_path.is_file():
        return {
            "status": "FAIL",
            "runtime": None,
            "scenario_count": 0,
            "error_code": "config_not_found",
            "error": _CONFIG_ERROR_MESSAGE,
        }

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        unreadable = isinstance(exc.__cause__, OSError)
        return {
            "status": "FAIL",
            "runtime": None,
            "scenario_count": 0,
            "error_code": "config_unreadable" if unreadable else "config_invalid",
            "error": _CONFIG_READ_ERROR_MESSAGE if unreadable else _CONFIG_ERROR_MESSAGE,
        }

    return {
        "status": "PASS",
        "runtime": config.runtime,
        "scenario_count": len(config.scenarios),
        "error_code": None,
        "error": None,
    }


def _redact_doctor_checks(checks: list[CheckResult]) -> list[CheckResult]:
    """Project local diagnostics onto shareable fields without mutating the originals."""

    redacted: list[CheckResult] = []
    for check in checks:
        name = check.name
        if name in REQUIRED_ROS_PACKAGES:
            message = _PACKAGE_INSTALLED_MESSAGE if check.ok else "package is unavailable"
        elif name in _CHECK_MESSAGES:
            message = _CHECK_MESSAGES[name][check.ok]
        else:
            # A future/custom check may use a private identifier as its name.
            name = "unknown"
            message = "additional check passed" if check.ok else "additional check failed"

        # Only the runtime check has a value consumed by build_report. Do not
        # propagate arbitrary values added by future local diagnostics.
        value = (
            check.value
            if name == "runtime" and check.value in ("native", "docker", "none")
            else None
        )
        redacted.append(
            CheckResult(name, check.ok, message, blocking=check.blocking, value=value)
        )
    return redacted


def build_support_bundle(
    *,
    config_path: Path,
    require_ros: bool | None = None,
) -> dict[str, object]:
    """Build a compact diagnostics bundle without project paths or scenario names."""

    config = _config_report(config_path)
    runtime = config["runtime"]
    if runtime in ("native", "docker"):
        checks = run_doctor_checks(require_ros=require_ros, runtime=cast(RuntimeName, runtime))
    else:
        # Invalid configs still get environment diagnostics, but never a PASS
        # bundle. Keep the default auto call compatible with existing callers.
        checks = run_doctor_checks(require_ros=require_ros)
    doctor = build_report(_redact_doctor_checks(checks))

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS"
        if doctor["status"] == "PASS" and config["status"] == "PASS"
        else "FAIL",
        "robotci_version": __version__,
        "environment": {
            "os": platform.system(),
            "python": platform.python_version(),
        },
        "doctor": doctor,
        "config": config,
        "privacy": {
            "includes_project_paths": False,
            "includes_scenario_names": False,
            "includes_environment_variables": False,
            "includes_credentials": False,
        },
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Write a compact, redaction-safe RobotCI support bundle for pilot diagnostics."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("robotci.yaml"),
        help="RobotCI config to validate (default: robotci.yaml).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".robotci") / "support-bundle.json",
        help=(
            "Destination JSON file (default: .robotci/support-bundle.json); use '-' for stdout."
        ),
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Write single-line JSON for CI logs, issue forms, or support tooling.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--require-ros",
        action="store_true",
        help="Require native ROS2 Jazzy/Nav2 readiness.",
    )
    mode.add_argument(
        "--runtime-optional",
        action="store_true",
        help="Collect runtime diagnostics without requiring a usable runtime.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    require_ros: bool | None = None
    if args.require_ros:
        require_ros = True
    elif args.runtime_optional:
        require_ros = False

    bundle = build_support_bundle(config_path=args.config, require_ros=require_ros)
    if args.compact:
        payload = json.dumps(bundle, sort_keys=True, separators=(",", ":")) + "\n"
    else:
        payload = json.dumps(bundle, indent=2, sort_keys=True) + "\n"

    if str(args.output) == "-":
        print(payload, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
        print(args.output)

    return 0 if bundle["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
