from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest
import yaml

from robotci.reproducibility import build_suite_execution_identity, validate_suite_execution

_ROOT = Path(__file__).resolve().parents[1]


def _environment(tmp_path: Path, *, candidate: str = "pass") -> dict[str, str]:
    fixtures = _ROOT / "tests" / "fixtures" / "gate-suite"
    shutil.copytree(fixtures / "baseline", tmp_path / "baseline")
    shutil.copytree(fixtures / candidate, tmp_path / "candidate")
    return {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "ROBOTCI_BASELINE": str(tmp_path / "baseline" / "suite-result.json"),
        "ROBOTCI_CANDIDATE": str(tmp_path / "candidate" / "suite-result.json"),
        "ROBOTCI_REPORT": str(tmp_path / "reports" / "report.json"),
        "ROBOTCI_SUMMARY": str(tmp_path / "reports" / "summary.md"),
        "ROBOTCI_JUNIT": str(tmp_path / "reports" / "junit.xml"),
        "ROBOTCI_MAX_DURATION": "10",
        "ROBOTCI_MAX_PATH": "10",
        "ROBOTCI_MAX_DISTANCE": "0.1",
        "ROBOTCI_MAX_STUCK": "0",
        "ROBOTCI_MAX_RECOVERIES": "0",
        "GITHUB_OUTPUT": str(tmp_path / "github-output"),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "github-summary"),
    }


def _run(
    environment: dict[str, str], *, cwd: Path = _ROOT
) -> subprocess.CompletedProcess[str]:
    # The shared developer interpreter may be installed from another checkout.
    # Bootstrap this explicit trusted source root without trusting cwd/PYTHONPATH;
    # the production Action instead imports its normally installed package.
    bootstrap = (
        "import runpy, sys; sys.path.insert(0, sys.argv[1]); "
        "runpy.run_module('robotci.action_gate', run_name='__main__')"
    )
    return subprocess.run(
        [sys.executable, "-I", "-c", bootstrap, str(_ROOT)],
        env=environment,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )


def _github_outputs(environment: dict[str, str]) -> str:
    output = Path(environment["GITHUB_OUTPUT"])
    return output.read_text(encoding="utf-8") if output.exists() else ""


@pytest.mark.parametrize("invalid", ["invalid_json", "missing_result", "incompatible_plan"])
def test_action_does_not_republish_previous_pass(tmp_path: Path, invalid: str) -> None:
    environment = _environment(tmp_path)
    first = _run(environment)
    assert first.returncode == 0, first.stderr + first.stdout
    assert json.loads(Path(environment["ROBOTCI_REPORT"]).read_text())["status"] == "PASS"
    assert "report=" in _github_outputs(environment)
    summary_path = Path(environment["GITHUB_STEP_SUMMARY"])
    first_summary = summary_path.read_bytes()
    assert "✅ **PASS**" in first_summary.decode("utf-8")

    candidate = Path(environment["ROBOTCI_CANDIDATE"])
    if invalid == "invalid_json":
        candidate.write_text("{", encoding="utf-8")
    elif invalid == "missing_result":
        (candidate.parent / "results" / "route.json").unlink()
    else:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
        execution = validate_suite_execution(payload)
        payload["execution"] = asdict(
            build_suite_execution_identity(
                runtime=execution.runtime,
                plan_fingerprint="sha256:" + "3" * 64,
                environment=execution.environment,
            )
        )
        candidate.write_text(json.dumps(payload), encoding="utf-8")
    inputs_before = {
        path: path.read_bytes()
        for root in (candidate.parent, Path(environment["ROBOTCI_BASELINE"]).parent)
        for path in root.rglob("*")
        if path.is_file()
    }
    # GitHub gives each step its own output file; the job summary may already
    # contain legitimate evidence from an earlier successful step.
    environment["GITHUB_OUTPUT"] = str(tmp_path / "second-github-output")
    second = _run(environment)

    assert second.returncode == 3, second.stderr + second.stdout
    assert _github_outputs(environment) == ""
    assert summary_path.read_bytes() == first_summary
    assert all(
        not Path(environment[name]).exists()
        for name in ("ROBOTCI_REPORT", "ROBOTCI_SUMMARY", "ROBOTCI_JUNIT")
    )
    assert all(path.read_bytes() == value for path, value in inputs_before.items())


@pytest.mark.parametrize(
    "overlap",
    ["baseline_suite", "candidate_suite", "baseline_result", "candidate_replay"],
)
def test_action_rejects_report_overlapping_input_before_cleanup(
    tmp_path: Path, overlap: str
) -> None:
    environment = _environment(tmp_path)
    paths = {
        "baseline_suite": Path(environment["ROBOTCI_BASELINE"]),
        "candidate_suite": Path(environment["ROBOTCI_CANDIDATE"]),
        "baseline_result": tmp_path / "baseline" / "results" / "route.json",
        "candidate_replay": tmp_path / "candidate" / "results" / "route.replay.json",
    }
    paths["candidate_replay"].write_text("recorded replay evidence", encoding="utf-8")
    stale_summary = Path(environment["ROBOTCI_SUMMARY"])
    stale_summary.parent.mkdir()
    stale_summary.write_text("old report", encoding="utf-8")
    environment["ROBOTCI_REPORT"] = str(paths[overlap])
    inputs_before = {path: path.read_bytes() for path in paths.values()}

    result = _run(environment)

    assert result.returncode == 3, result.stderr + result.stdout
    assert "overlaps suite evidence" in result.stderr
    assert _github_outputs(environment) == ""
    assert not Path(environment["GITHUB_STEP_SUMMARY"]).exists()
    assert stale_summary.read_text(encoding="utf-8") == "old report"
    assert all(path.read_bytes() == value for path, value in inputs_before.items())


@pytest.mark.parametrize("alias", ["symlink", "hardlink"])
def test_action_rejects_report_alias_of_input(tmp_path: Path, alias: str) -> None:
    environment = _environment(tmp_path)
    destination = Path(environment["ROBOTCI_REPORT"])
    destination.parent.mkdir()
    evidence = tmp_path / "baseline" / "results" / "route.json"
    evidence_before = evidence.read_bytes()
    try:
        if alias == "symlink":
            destination.symlink_to(evidence)
        else:
            destination.hardlink_to(evidence)
    except OSError as exc:
        pytest.skip(f"filesystem does not support {alias}: {exc}")

    result = _run(environment)

    assert result.returncode == 3, result.stderr + result.stdout
    assert _github_outputs(environment) == ""
    assert evidence.read_bytes() == evidence_before
    assert destination.read_bytes() == evidence_before


def test_action_publishes_current_regression_before_blocking(tmp_path: Path) -> None:
    environment = _environment(tmp_path, candidate="regression")

    result = _run(environment)

    assert result.returncode == 4, result.stderr + result.stdout
    assert json.loads(Path(environment["ROBOTCI_REPORT"]).read_text())["status"] == "REGRESSION"
    outputs = _github_outputs(environment)
    for name, variable in (
        ("report", "ROBOTCI_REPORT"),
        ("summary", "ROBOTCI_SUMMARY"),
        ("junit", "ROBOTCI_JUNIT"),
    ):
        assert f"{name}={environment[variable]}\n" in outputs
        assert Path(environment[variable]).is_file()
    assert "❌ **REGRESSION**" in Path(environment["GITHUB_STEP_SUMMARY"]).read_text(
        encoding="utf-8"
    )


def test_action_removes_partial_reports_after_write_failure(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    blocked_parent = tmp_path / "blocked-parent"
    blocked_parent.write_text("regular file", encoding="utf-8")
    environment["ROBOTCI_SUMMARY"] = str(blocked_parent / "summary.md")

    result = _run(environment)

    assert result.returncode == 3, result.stderr + result.stdout
    assert _github_outputs(environment) == ""
    assert not Path(environment["GITHUB_STEP_SUMMARY"]).exists()
    assert not Path(environment["ROBOTCI_REPORT"]).exists()
    assert not Path(environment["ROBOTCI_JUNIT"]).exists()
    assert blocked_parent.read_text(encoding="utf-8") == "regular file"


def test_composite_action_uses_current_invocation_report_wrapper() -> None:
    action = yaml.safe_load((_ROOT / "action.yml").read_text(encoding="utf-8"))
    gate = next(step for step in action["runs"]["steps"] if step.get("id") == "gate")
    assert gate["run"].strip() == "python -I -m robotci.action_gate"
    install = next(step for step in action["runs"]["steps"] if step["name"] == "Install RobotCI")
    assert install["run"] == 'python -I -m pip install "${{ github.action_path }}"'


@pytest.mark.parametrize("suite_name", ["baseline", "candidate"])
@pytest.mark.parametrize("layout", ["measurements/route.json", "route.json"])
@pytest.mark.parametrize("kind", ["result", "replay"])
@pytest.mark.parametrize("alias", ["direct", "hardlink", "symlink"])
def test_action_preserves_declared_evidence_outside_default_results_directory(
    tmp_path: Path, suite_name: str, layout: str, kind: str, alias: str
) -> None:
    environment = _environment(tmp_path)
    suite_path = tmp_path / suite_name / "suite-result.json"
    result_path = suite_path.parent / layout
    result_path.parent.mkdir(exist_ok=True)
    shutil.copyfile(suite_path.parent / "results" / "route.json", result_path)
    payload = json.loads(suite_path.read_text(encoding="utf-8"))
    payload["scenarios"][0]["result_file"] = layout
    suite_path.write_text(json.dumps(payload), encoding="utf-8")
    replay_path = result_path.with_suffix(".replay.json")
    replay_path.write_text("recorded replay evidence", encoding="utf-8")
    # Each input's closure is protected independently, even if the other suite
    # or the referenced result cannot participate in a valid comparison.
    other_suite = tmp_path / ("candidate" if suite_name == "baseline" else "baseline")
    (other_suite / "suite-result.json").write_text("{", encoding="utf-8")
    evidence = result_path if kind == "result" else replay_path
    before = {path: path.read_bytes() for path in (suite_path, result_path, replay_path)}
    stale_summary = Path(environment["ROBOTCI_SUMMARY"])
    stale_summary.parent.mkdir()
    stale_summary.write_text("previous report", encoding="utf-8")
    destination = evidence if alias == "direct" else Path(environment["ROBOTCI_REPORT"])
    try:
        if alias == "hardlink":
            destination.hardlink_to(evidence)
        elif alias == "symlink":
            destination.symlink_to(evidence)
    except OSError as exc:
        pytest.skip(f"filesystem does not support {alias}: {exc}")
    environment["ROBOTCI_REPORT"] = str(destination)

    result = _run(environment)

    assert result.returncode == 3, result.stderr + result.stdout
    assert "RobotCI action report error" in result.stderr
    assert _github_outputs(environment) == ""
    assert not Path(environment["GITHUB_STEP_SUMMARY"]).exists()
    assert stale_summary.read_text(encoding="utf-8") == "previous report"
    assert all(path.read_bytes() == content for path, content in before.items())
    assert destination.read_bytes() == before[evidence]


def test_action_summary_write_failure_does_not_advertise_removed_reports(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    blocked_parent = tmp_path / "blocked-parent"
    blocked_parent.write_text("regular file", encoding="utf-8")
    environment["GITHUB_STEP_SUMMARY"] = str(blocked_parent / "summary.md")

    result = _run(environment)

    assert result.returncode == 3, result.stderr + result.stdout
    assert _github_outputs(environment) == ""
    assert all(
        not Path(environment[name]).exists()
        for name in ("ROBOTCI_REPORT", "ROBOTCI_SUMMARY", "ROBOTCI_JUNIT")
    )
    assert blocked_parent.read_text(encoding="utf-8") == "regular file"


def test_action_ignores_fake_robotci_package_in_caller_workspace(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    workspace = tmp_path / "foreign-workspace"
    package = workspace / "robotci"
    package.mkdir(parents=True)
    marker = workspace / "untrusted-package-ran"
    fake = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
    (package / "__init__.py").write_text(fake, encoding="utf-8")
    for module in ("action_gate.py", "suite_cli.py"):
        (package / module).write_text(fake + "raise SystemExit(0)\n", encoding="utf-8")
    environment["PYTHONPATH"] = str(workspace)

    result = _run(environment, cwd=workspace)

    assert result.returncode == 0, result.stderr + result.stdout
    assert not marker.exists()
    assert json.loads(Path(environment["ROBOTCI_REPORT"]).read_text())["status"] == "PASS"
    assert "report=" in _github_outputs(environment)
