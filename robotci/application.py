from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from robotci import __version__
from robotci.baselines import DEFAULT_BASELINE_ROOT, baseline_suite_path
from robotci.comparison import compare_scenario_result_files
from robotci.config import RobotCIConfig, ScenarioConfig, load_config
from robotci.doctor import CheckResult, run_doctor_checks
from robotci.paths import state_dir
from robotci.project import DEFAULT_CONFIG_PATH, ProjectContext, resolve_project_context
from robotci.regression import RegressionPolicy, RegressionReport
from robotci.reproducibility import SuiteExecutionIdentity
from robotci.result_schema import ValidatedScenarioResult, load_result
from robotci.results import ScenarioStatus
from robotci.suite_comparison import SuiteRegressionReport, compare_suite_result_files
from robotci.suite_schema import SuiteResultError, SuiteResultErrorCode, load_suite_result

DiagnosticStatus = Literal["PASS", "FAIL"]


class ApplicationError(ValueError):
    """Raised when persisted application data cannot be read safely."""

    def __init__(
        self,
        message: str,
        *,
        code: SuiteResultErrorCode | None = None,
        path: Path | None = None,
        field: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.path = path
        self.field = field

    def as_dict(self) -> dict[str, str]:
        details = {"message": str(self)}
        if self.code is not None:
            details["code"] = self.code
        if self.path is not None:
            details["path"] = str(self.path)
        if self.field is not None:
            details["field"] = self.field
        return details


@dataclass(frozen=True)
class ProjectInfo:
    robotci_version: str
    project_root: Path
    config_path: Path
    state_path: Path
    latest_suite_path: Path
    config: RobotCIConfig


@dataclass(frozen=True)
class SuiteScenarioSummary:
    scenario: str
    status: ScenarioStatus
    duration_sec: float
    result_path: Path


@dataclass(frozen=True)
class SuiteResultSnapshot:
    path: Path
    schema_version: int
    status: ScenarioStatus
    runtime: Literal["native", "docker"]
    duration_sec: float
    scenarios: tuple[SuiteScenarioSummary, ...]
    execution: SuiteExecutionIdentity


@dataclass(frozen=True)
class DiagnosticReport:
    checks: tuple[CheckResult, ...]

    @property
    def status(self) -> DiagnosticStatus:
        if any(check.blocking and not check.ok for check in self.checks):
            return "FAIL"
        return "PASS"

    @property
    def selected_runtime(self) -> str | None:
        runtime = next((check for check in self.checks if check.name == "runtime"), None)
        return runtime.value if runtime is not None else None


class RobotCIApplication:
    """Typed application facade over RobotCI's existing deterministic core."""

    def __init__(
        self,
        config_path: str | Path = DEFAULT_CONFIG_PATH,
        *,
        project_root: str | Path | None = None,
    ) -> None:
        self._context = resolve_project_context(config_path, project_root=project_root)

    @property
    def context(self) -> ProjectContext:
        return self._context

    def get_project_info(self) -> ProjectInfo:
        config = self._load_config()
        project_state = state_dir(self._context.project_root).resolve()
        return ProjectInfo(
            robotci_version=__version__,
            project_root=self._context.project_root,
            config_path=self._context.config_path,
            state_path=project_state,
            latest_suite_path=project_state / "suite-result.json",
            config=config,
        )

    def list_scenarios(self) -> tuple[ScenarioConfig, ...]:
        return self._load_config().scenarios

    def get_latest_suite_result(self) -> SuiteResultSnapshot:
        return self._load_suite_result(self._latest_suite_path())

    def get_scenario_result(
        self,
        scenario: str,
        *,
        suite_path: str | Path | None = None,
    ) -> ValidatedScenarioResult:
        suite = self._load_suite_result(
            self._latest_suite_path()
            if suite_path is None
            else self._resolve_project_path(suite_path)
        )
        summary = next(
            (entry for entry in suite.scenarios if entry.scenario == scenario),
            None,
        )
        if summary is None:
            available = ", ".join(entry.scenario for entry in suite.scenarios)
            raise ApplicationError(
                f"scenario {scenario!r} is not present in suite result; available: {available}"
            )

        result = load_result(summary.result_path)
        if result.scenario != summary.scenario:
            raise ApplicationError(
                f"suite scenario {summary.scenario!r} points to result for "
                f"{result.scenario!r}"
            )
        return result

    def compare_scenario_results(
        self,
        *,
        baseline_path: str | Path,
        candidate_path: str | Path,
        policy: RegressionPolicy | None = None,
    ) -> RegressionReport:
        return compare_scenario_result_files(
            baseline_path=self._resolve_project_path(baseline_path),
            candidate_path=self._resolve_project_path(candidate_path),
            policy=policy,
        )

    def compare_suite_results(
        self,
        *,
        baseline_path: str | Path,
        candidate_path: str | Path,
        policy: RegressionPolicy | None = None,
    ) -> SuiteRegressionReport:
        return compare_suite_result_files(
            baseline_path=self._resolve_project_path(baseline_path),
            candidate_path=self._resolve_project_path(candidate_path),
            policy=policy,
        )

    def compare_to_baseline(
        self,
        name: str,
        *,
        candidate_suite_path: str | Path | None = None,
        store_root: str | Path = DEFAULT_BASELINE_ROOT,
        policy: RegressionPolicy | None = None,
    ) -> SuiteRegressionReport:
        baseline_root = self._resolve_project_path(store_root)
        baseline_path = baseline_suite_path(name, store_root=baseline_root)
        candidate_path = (
            self._latest_suite_path()
            if candidate_suite_path is None
            else self._resolve_project_path(candidate_suite_path)
        )
        return compare_suite_result_files(
            baseline_path=baseline_path,
            candidate_path=candidate_path,
            policy=policy,
        )

    def get_diagnostics(self, *, require_ros: bool | None = None) -> DiagnosticReport:
        return DiagnosticReport(tuple(run_doctor_checks(require_ros=require_ros)))

    def _load_config(self) -> RobotCIConfig:
        return load_config(self._context.config_path)

    def _latest_suite_path(self) -> Path:
        return (state_dir(self._context.project_root) / "suite-result.json").resolve()

    def _resolve_project_path(self, path: str | Path) -> Path:
        requested = Path(path).expanduser()
        if requested.is_absolute():
            return requested.resolve()
        return (self._context.project_root / requested).resolve()

    def _load_suite_result(self, path: Path) -> SuiteResultSnapshot:
        try:
            suite = load_suite_result(path)
        except SuiteResultError as exc:
            raise ApplicationError(
                str(exc),
                code=exc.code,
                path=exc.path,
                field=exc.field,
            ) from exc
        return SuiteResultSnapshot(
            path=suite.path,
            schema_version=suite.schema_version,
            status=suite.status,
            runtime=suite.runtime,
            duration_sec=suite.duration_sec,
            scenarios=tuple(
                SuiteScenarioSummary(
                    scenario=item.scenario,
                    status=item.status,
                    duration_sec=item.duration_sec,
                    result_path=item.result_path,
                )
                for item in suite.scenarios
            ),
            execution=suite.execution,
        )
