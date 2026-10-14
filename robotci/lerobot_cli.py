"""Offline metadata preflight; never import LeRobot or open hardware."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from robotci.lerobot_inspect import LeRobotInspectionError, inspect_lerobot

lerobot_app = typer.Typer(help="Inspect local LeRobot metadata without training or hardware.")


@lerobot_app.command("inspect")
def inspect_command(
    dataset: Annotated[Path, typer.Argument(help="Dataset directory or meta/info.json.")],
    policy: Annotated[
        Path | None,
        typer.Option("--policy", help="Optional pretrained policy config.json or its directory."),
    ] = None,
    expected_robot_type: Annotated[
        str | None, typer.Option("--robot-type", help="Expected dataset robot_type.")
    ] = None,
    expected_fps: Annotated[
        int | None, typer.Option("--fps", help="Expected dataset frame rate.")
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Emit a versioned JSON report.")] = False,
) -> None:
    """Check metadata and optional policy feature compatibility (exit 0 or 3)."""
    try:
        report = inspect_lerobot(
            dataset,
            policy,
            expected_robot_type=expected_robot_type,
            expected_fps=expected_fps,
        )
    except LeRobotInspectionError as exc:
        report = {
            "schema_version": 1,
            "scope": "metadata_only",
            "status": "INVALID",
            "issues": [
                {"severity": "error", "code": "input_error", "path": "input", "message": str(exc)}
            ],
        }
    if as_json:
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    else:
        typer.echo(f"LeRobot: {report['status']} (только метаданные)")
        dataset_info = report.get("dataset") or {}
        if dataset_info:
            typer.echo(
                f"Датасет: {dataset_info['codebase_version']}; "
                f"робот: {dataset_info['robot_type']}; FPS: {dataset_info['fps']}"
            )
            typer.echo(
                f"Заявлено эпизодов: {dataset_info['total_episodes']}; "
                f"кадров: {dataset_info['total_frames']}"
            )
            policy_info = report.get("policy")
            if policy_info is not None:
                typer.echo(
                    f"Политика: {policy_info['type']}; "
                    f"сопоставлено features: {len(policy_info['checked_features'])}"
                )
        for issue in report["issues"]:
            typer.echo(f"{issue['severity']}: {issue['path']}: {issue['message']}")
        typer.echo(
            "Файлы эпизодов, видео, веса и управление роботом не проверены. "
            "Это не результат симуляции и не допуск к запуску на оборудовании."
        )
    if report["status"] != "VALID":
        raise typer.Exit(code=3)
