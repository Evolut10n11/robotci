from __future__ import annotations

import argparse
import json
import platform
import sys
from collections.abc import Sequence
from pathlib import Path

from robotci import __version__
from robotci.config import ConfigError, load_config
from robotci.doctor import run_doctor_checks
from robotci.doctor_report import build_report

SCHEMA_VERSION = 1
_CONFIG_ERROR_MESSAGE = "RobotCI config is invalid; run 'robotci validate' locally for details"


def _config_report(config_path: Path) -> dict[str, object]:
    try:
        config = load_config(config_path)
    except ConfigError:
        return {
            "status": "FAIL",
            "runtime": None,
            "scenario_count": 0,
            "error": _CONFIG_ERROR_MESSAGE,
        }

    return {
        "status": "PASS",
        "runtime": config.runtime,
        "scenario_count": len(config.scenarios),
        "error": None,
    }


def build_support_bundle(
    *,
    config_path: Path,
    require_ros: bool | None = None,
) -> dict[str, object]:
    """Build a compact diagnostics bundle without project paths or scenario names."""

    doctor = build_report(run_doctor_checks(require_ros=require_ros))
    config = _config_report(config_path)

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
