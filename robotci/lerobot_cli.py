"""LeRobot preflight, explicit checkpoint fetching and optional CPU PushT evaluation."""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Annotated

import typer

from robotci.lerobot_inspect import LeRobotInspectionError, inspect_lerobot

lerobot_app = typer.Typer(help="Inspect LeRobot metadata and compare optional CPU PushT runs.")


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


def _json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _infra_report(message: str, artifact_type: str) -> dict:
    return {
        "schema_version": 1,
        "artifact_type": artifact_type,
        "status": "INFRA_ERROR",
        "findings": [{"code": "input_or_runtime_error", "message": message}],
    }


@lerobot_app.command("fetch")
def fetch_command(
    destination: Annotated[
        Path, typer.Argument(help="Directory for the pinned public Diffusion PushT checkpoint.")
    ],
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit the verified source manifest.")
    ] = False,
) -> None:
    """Explicitly download ~1.05 GB from Hugging Face; verify exact sizes and SHA-256."""
    from robotci.lerobot_checkpoint import LeRobotCheckpointError, fetch_checkpoint

    try:
        manifest = fetch_checkpoint(destination)
    except LeRobotCheckpointError as exc:
        typer.echo(_json(_infra_report(str(exc), "lerobot_checkpoint")))
        raise typer.Exit(code=3) from exc
    if as_json:
        typer.echo(_json(manifest), nl=False)
    else:
        typer.echo(f"Checkpoint проверен: {destination}")
        typer.echo(f"Источник: {manifest['source']['repo_id']}@{manifest['source']['revision']}")
        typer.echo("SHA-256 обоих файлов совпадает; скачивание не является оценкой политики.")


@lerobot_app.command("run")
def run_command(
    checkpoint: Annotated[Path, typer.Argument(help="Local checkpoint prepared by lerobot fetch.")],
    output: Annotated[Path, typer.Option("--output", help="New run directory; never overwrite.")],
    seeds: Annotated[
        list[int] | None,
        typer.Option("--seed", min=0, max=2**32 - 1, help="Repeat for seeds (default 1000–1002)."),
    ] = None,
    max_steps: Annotated[
        int, typer.Option("--max-steps", min=1, max=1000, help="Maximum steps per seed.")
    ] = 300,
    inference_steps: Annotated[
        int, typer.Option("--inference-steps", min=1, max=100, help="DDPM denoising steps.")
    ] = 10,
    action_scale: Annotated[
        float,
        typer.Option("--action-scale", min=0.0, max=1.0, help="1: policy targets; 0: hold."),
    ] = 1.0,
    threads: Annotated[
        int, typer.Option("--threads", min=1, max=32, help="CPU Torch threads (part of protocol).")
    ] = 1,
    as_json: Annotated[bool, typer.Option("--json", help="Print the complete run result.")] = False,
) -> None:
    """Run the real trained policy in local PushT; optional ML dependencies are required."""
    from robotci.lerobot_checkpoint import LeRobotCheckpointError
    from robotci.lerobot_runner import LeRobotRunnerError, run_pusht

    try:
        if not math.isfinite(action_scale):
            raise LeRobotRunnerError("action_scale must be finite")
        result = run_pusht(
            checkpoint,
            output,
            seeds=seeds if seeds is not None else [1000, 1001, 1002],
            max_steps=max_steps,
            num_inference_steps=inference_steps,
            action_scale=action_scale,
            torch_threads=threads,
        )
    except (LeRobotRunnerError, LeRobotCheckpointError) as exc:
        result = _infra_report(str(exc), "lerobot_pusht_evaluation")
    if as_json or result["status"] != "COMPLETED":
        typer.echo(_json(result), nl=False)
    else:
        episodes = result["episodes"]
        successes = sum(episode["success"] for episode in episodes)
        reward = sum(episode["max_reward"] for episode in episodes) / len(episodes)
        typer.echo(
            f"PushT: {successes}/{len(episodes)} успешных эпизодов; mean max reward={reward:.6f}"
        )
        typer.echo(f"Результат: {output / 'result.json'}")
        typer.echo("Для проверки регрессии сравните совместимые baseline и candidate.")
    if result["status"] != "COMPLETED":
        raise typer.Exit(code=3)


def _save_reports(report: dict, output: Path | None, markdown: Path | None) -> None:
    from robotci.lerobot_evaluation import LeRobotEvaluationError, format_comparison_markdown

    paths = [path for path in (output, markdown) if path is not None]
    if len({path.resolve() for path in paths}) != len(paths):
        raise LeRobotEvaluationError("JSON and Markdown reports need different output paths")
    for path in paths:
        if path.exists() or path.is_symlink():
            raise LeRobotEvaluationError(f"Report already exists: {path}")
    staged: list[tuple[Path, Path]] = []
    published: list[Path] = []
    try:
        # Prepare both outputs before publishing either; the machine-readable report is last.
        for path, content in (
            (markdown, format_comparison_markdown(report) if markdown is not None else ""),
            (output, _json(report)),
        ):
            if path is not None:
                path = path.resolve()
                path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
                ) as target:
                    temporary = Path(target.name)
                    staged.append((temporary, path))
                    target.write(content)
                # Hard links publish a complete file atomically and refuse existing names.
        for temporary, path in staged:
            os.link(temporary, path)
            published.append(path)
    except OSError:
        for path in published:
            path.unlink(missing_ok=True)
        raise
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)


@lerobot_app.command("compare")
def compare_command(
    baseline: Annotated[Path, typer.Argument(help="Known-good run directory or result.json.")],
    candidate: Annotated[Path, typer.Argument(help="Candidate run directory or result.json.")],
    max_success_rate_drop: Annotated[
        float, typer.Option(min=0.0, max=1.0, help="Allowed absolute success-rate drop.")
    ] = 0.0,
    max_reward_drop: Annotated[
        float, typer.Option(min=0.0, max=1.0, help="Allowed absolute mean-max-reward drop.")
    ] = 0.05,
    output: Annotated[
        Path | None, typer.Option("--output", help="Write a new JSON comparison report.")
    ] = None,
    markdown: Annotated[
        Path | None, typer.Option("--markdown", help="Write a new Markdown comparison report.")
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the JSON comparison report.")
    ] = False,
) -> None:
    """Compare compatible recorded episodes: exit 0 PASS, 4 REGRESSION, 3 INFRA_ERROR."""
    from robotci.lerobot_evaluation import (
        LeRobotEvaluationError,
        compare_evaluations,
        format_comparison_markdown,
        load_evaluation,
    )

    try:
        baseline_path = baseline / "result.json" if baseline.is_dir() else baseline
        candidate_path = candidate / "result.json" if candidate.is_dir() else candidate
        report = compare_evaluations(
            load_evaluation(baseline_path),
            load_evaluation(candidate_path),
            max_success_rate_drop=max_success_rate_drop,
            max_reward_drop=max_reward_drop,
        )
    except (LeRobotEvaluationError, OSError) as exc:
        report = _infra_report(str(exc), "lerobot_pusht_comparison")
    try:
        _save_reports(report, output, markdown)
    except (LeRobotEvaluationError, OSError) as exc:
        report = _infra_report(str(exc), "lerobot_pusht_comparison")
    typer.echo(_json(report) if as_json else format_comparison_markdown(report), nl=False)
    code = {"PASS": 0, "REGRESSION": 4, "INFRA_ERROR": 3}[report["status"]]
    if code:
        raise typer.Exit(code=code)
