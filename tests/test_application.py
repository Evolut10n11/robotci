from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from robotci.application import ApplicationError, DiagnosticReport, RobotCIApplication
from robotci.baselines import capture_baseline
from robotci.doctor import CheckResult

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "gate-suite"


def _write_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """\
version: 1
runtime: docker
scenarios:
  - name: route
    map_id: nav2-loopback
    start: {x: 0.0, y: 0.0}
    goal: {x: 1.0, y: 0.0}
    timeout_sec: 30
""",
        encoding="utf-8",
    )
    return path


def _copy_suite(project: Path, fixture: str = "pass") -> Path:
    state = project / ".robotci"
    shutil.copytree(FIXTURE_ROOT / fixture, state)
    return state / "suite-result.json"


def test_project_info_and_scenarios_use_resolved_project_context(tmp_path: Path) -> None:
    project = tmp_path / "project"
    config_path = _write_config(project / "robotci.yaml")
    application = RobotCIApplication(project_root=project)

    info = application.get_project_info()
    scenarios = application.list_scenarios()

    assert info.project_root == project.resolve()
    assert info.config_path == config_path.resolve()
    assert info.state_path == (project / ".robotci").resolve()
    assert info.latest_suite_path == (project / ".robotci" / "suite-result.json").resolve()
    assert info.config.runtime == "docker"
    assert info.robotci_version
    assert scenarios == info.config.scenarios
    assert scenarios[0].name == "route"


def test_reads_latest_suite_and_its_scenario_result(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_config(project / "robotci.yaml")
    suite_path = _copy_suite(project)
    application = RobotCIApplication(project_root=project)

    suite = application.get_latest_suite_result()
    result = application.get_scenario_result("route")

    assert suite.path == suite_path.resolve()
    assert suite.status == "PASS"
    assert suite.runtime == "native"
    assert suite.scenarios[0].scenario == "route"
    assert suite.scenarios[0].result_path == (project / ".robotci/results/route.json").resolve()
    assert result.scenario == "route"
    assert result.status == "PASS"
    assert result.metrics is not None
    assert result.metrics.path_length_m == 5.2


def test_scenario_result_reports_names_available_in_suite(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_config(project / "robotci.yaml")
    _copy_suite(project)
    application = RobotCIApplication(project_root=project)

    with pytest.raises(ApplicationError, match="available: route"):
        application.get_scenario_result("missing")


def test_suite_reader_rejects_result_path_escape(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_config(project / "robotci.yaml")
    suite_path = _copy_suite(project)
    payload = json.loads(suite_path.read_text(encoding="utf-8"))
    payload["scenarios"][0]["result_file"] = "../outside.json"
    suite_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ApplicationError, match="unsafe result_file path"):
        RobotCIApplication(project_root=project).get_latest_suite_result()


def test_comparison_methods_reuse_scenario_and_suite_core_logic(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_config(project / "robotci.yaml")
    baseline_suite = tmp_path / "baseline" / "suite-result.json"
    candidate_suite = tmp_path / "candidate" / "suite-result.json"
    shutil.copytree(FIXTURE_ROOT / "baseline", baseline_suite.parent)
    shutil.copytree(FIXTURE_ROOT / "regression", candidate_suite.parent)
    application = RobotCIApplication(project_root=project)

    scenario_report = application.compare_scenario_results(
        baseline_path=baseline_suite.parent / "results/route.json",
        candidate_path=candidate_suite.parent / "results/route.json",
    )
    suite_report = application.compare_suite_results(
        baseline_path=baseline_suite,
        candidate_path=candidate_suite,
    )

    assert scenario_report.status == "REGRESSION"
    assert suite_report.status == "REGRESSION"


def test_compares_latest_suite_to_project_baseline(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_config(project / "robotci.yaml")
    latest_suite = _copy_suite(project, "regression")
    baseline_source = tmp_path / "baseline-source"
    shutil.copytree(FIXTURE_ROOT / "baseline", baseline_source)
    capture_baseline(
        "known-good",
        baseline_source / "suite-result.json",
        store_root=project / ".robotci/baselines",
    )

    report = RobotCIApplication(project_root=project).compare_to_baseline("known-good")

    assert latest_suite.is_file()
    assert report.status == "REGRESSION"


def test_diagnostics_return_typed_report_without_terminal_formatting(monkeypatch) -> None:
    checks = [
        CheckResult("platform", True, "supported"),
        CheckResult("docker", False, "not available", blocking=False),
        CheckResult("runtime", True, "auto runtime will use native", value="native"),
    ]
    received: list[bool | None] = []

    def fake_checks(*, require_ros: bool | None = None) -> list[CheckResult]:
        received.append(require_ros)
        return checks

    monkeypatch.setattr("robotci.application.run_doctor_checks", fake_checks)

    report = RobotCIApplication().get_diagnostics(require_ros=False)

    assert isinstance(report, DiagnosticReport)
    assert report.checks == tuple(checks)
    assert report.status == "PASS"
    assert report.selected_runtime == "native"
    assert received == [False]


def test_diagnostics_fail_only_for_blocking_checks() -> None:
    report = DiagnosticReport(
        (
            CheckResult("docker", False, "not available", blocking=False),
            CheckResult("runtime", False, "no runtime", blocking=True, value="none"),
        )
    )

    assert report.status == "FAIL"
    assert report.selected_runtime == "none"
