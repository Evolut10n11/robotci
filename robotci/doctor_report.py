from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path

from robotci.doctor import CheckResult, run_doctor_checks

SCHEMA_VERSION = 1


def _adapter_override_enabled() -> bool:
    return bool(os.environ.get("ROBOTCI_ATTEMPT_SCRIPT"))


def build_report(checks: list[CheckResult]) -> dict[str, object]:
    blocking_failures = [check for check in checks if check.blocking and not check.ok]
    runtime = next((check for check in checks if check.name == "runtime"), None)

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS" if not blocking_failures else "FAIL",
        "runtime": {
            "ok": runtime.ok,
            "selected": runtime.value,
            "message": runtime.message,
            "adapter_override": (
                runtime.value == "native" and _adapter_override_enabled()
            ),
        }
        if runtime is not None
        else None,
        "checks": [
            {
                "name": check.name,
                "ok": check.ok,
                "blocking": check.blocking,
                "message": check.message,
            }
            for check in checks
        ],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write RobotCI doctor diagnostics as machine-readable JSON."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--require-ros",
        action="store_true",
        help=(
            "Require a native ROS2 Jazzy/Nav2 runtime; Docker fallback does not satisfy "
            "this mode."
        ),
    )
    mode.add_argument(
        "--runtime-optional",
        action="store_true",
        help=(
            "Report runtime diagnostics without failing when neither native ROS nor Docker "
            "is ready."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write JSON to this path instead of stdout.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    require_ros: bool | None = None
    if args.require_ros:
        require_ros = True
    elif args.runtime_optional:
        require_ros = False

    report = build_report(run_doctor_checks(require_ros=require_ros))
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"

    if args.output is None:
        print(payload, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")

    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())