from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal, Never, cast

from robotci.reproducibility import (
    SUITE_RESULT_SCHEMA_VERSION,
    ReproducibilityError,
    SuiteExecutionIdentity,
    validate_suite_execution,
)
from robotci.results import ScenarioStatus

SuiteResultErrorCode = Literal[
    "suite_not_found",
    "read_error",
    "invalid_json",
    "invalid_metadata",
    "unsupported_schema_version",
    "unsafe_result_path",
    "missing_result_file",
]


class SuiteResultError(ValueError):
    """A structured failure raised while loading a suite result."""

    def __init__(
        self,
        code: SuiteResultErrorCode,
        message: str,
        *,
        path: Path,
        field: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.path = path
        self.field = field

    def as_dict(self) -> dict[str, str]:
        details = {
            "code": self.code,
            "message": str(self),
            "path": str(self.path),
        }
        if self.field is not None:
            details["field"] = self.field
        return details


@dataclass(frozen=True)
class ValidatedSuiteScenarioResult:
    scenario: str
    status: ScenarioStatus
    duration_sec: float
    result_file: str
    result_path: Path


@dataclass(frozen=True)
class ValidatedSuiteResult:
    path: Path
    schema_version: int
    status: ScenarioStatus
    runtime: Literal["native", "docker"]
    duration_sec: float
    scenarios: tuple[ValidatedSuiteScenarioResult, ...]
    execution: SuiteExecutionIdentity


class _InvalidJSONValue(ValueError):
    pass


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise _InvalidJSONValue(f"duplicate JSON key: {key!r}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> object:
    raise _InvalidJSONValue(f"invalid non-finite JSON number: {value}")


def _raise_metadata_error(
    message: str,
    *,
    path: Path,
    field: str | None = None,
) -> Never:
    raise SuiteResultError(
        "invalid_metadata",
        message,
        path=path,
        field=field,
    )


def _scenario_status(value: object, name: str, *, path: Path) -> ScenarioStatus:
    if value not in {"PASS", "FAIL", "TIMEOUT", "INFRA_ERROR"}:
        _raise_metadata_error(
            f"{name} has unsupported status {value!r}",
            path=path,
            field=name,
        )
    return cast(ScenarioStatus, value)


def _duration(value: object, name: str, *, path: Path) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        _raise_metadata_error(
            f"{name} must be a non-negative finite number",
            path=path,
            field=name,
        )
    try:
        duration = float(value)
    except OverflowError:
        _raise_metadata_error(
            f"{name} must be a non-negative finite number",
            path=path,
            field=name,
        )
    if not math.isfinite(duration) or duration < 0:
        _raise_metadata_error(
            f"{name} must be a non-negative finite number",
            path=path,
            field=name,
        )
    return duration


def _safe_result_path(
    *,
    suite_path: Path,
    result_file: str,
    field: str,
) -> Path:
    native = Path(result_file)
    posix = PurePosixPath(result_file)
    windows = PureWindowsPath(result_file)
    if (
        native.is_absolute()
        or posix.is_absolute()
        or bool(windows.anchor)
        or ".." in posix.parts
        or ".." in windows.parts
    ):
        raise SuiteResultError(
            "unsafe_result_path",
            f"suite result contains unsafe result_file path: {result_file}",
            path=suite_path,
            field=field,
        )

    suite_root = suite_path.parent.resolve()
    results_root = (suite_root / "results").resolve()
    resolved = (suite_path.parent / native).resolve()
    try:
        results_root.relative_to(suite_root)
        resolved.relative_to(results_root)
    except ValueError as exc:
        raise SuiteResultError(
            "unsafe_result_path",
            "suite result result_file escapes suite results directory: "
            f"{result_file}",
            path=suite_path,
            field=field,
        ) from exc
    return resolved


def _load_json_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
    except FileNotFoundError as exc:
        raise SuiteResultError(
            "suite_not_found",
            f"suite result does not exist: {path}",
            path=path,
        ) from exc
    except OSError as exc:
        raise SuiteResultError(
            "read_error",
            f"cannot read suite result '{path}': {exc}",
            path=path,
        ) from exc
    except UnicodeError as exc:
        raise SuiteResultError(
            "invalid_json",
            f"suite result is not valid UTF-8 '{path}': {exc}",
            path=path,
        ) from exc
    except (json.JSONDecodeError, _InvalidJSONValue) as exc:
        raise SuiteResultError(
            "invalid_json",
            f"invalid JSON in suite result '{path}': {exc}",
            path=path,
        ) from exc
    if not isinstance(payload, dict):
        raise SuiteResultError(
            "invalid_metadata",
            "suite result must contain a JSON object",
            path=path,
        )
    return payload


def load_suite_result(path: str | Path) -> ValidatedSuiteResult:
    """Load and validate a supported suite-result.json and its result references."""

    suite_path = Path(path).resolve()
    payload = _load_json_object(suite_path)

    version = payload.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        _raise_metadata_error(
            f"suite result.schema_version must be {SUITE_RESULT_SCHEMA_VERSION}",
            path=suite_path,
            field="schema_version",
        )
    if version != SUITE_RESULT_SCHEMA_VERSION:
        raise SuiteResultError(
            "unsupported_schema_version",
            f"unsupported suite result.schema_version {version}; "
            f"supported version is {SUITE_RESULT_SCHEMA_VERSION}",
            path=suite_path,
            field="schema_version",
        )

    try:
        execution = validate_suite_execution(payload)
    except ReproducibilityError as exc:
        raise SuiteResultError(
            "invalid_metadata",
            str(exc),
            path=suite_path,
            field="execution",
        ) from exc

    status = _scenario_status(payload.get("status"), "suite result.status", path=suite_path)
    duration_sec = _duration(
        payload.get("duration_sec"),
        "suite result.duration_sec",
        path=suite_path,
    )
    raw_scenarios = payload.get("scenarios")
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        _raise_metadata_error(
            "suite result.scenarios must be a non-empty array",
            path=suite_path,
            field="scenarios",
        )

    scenarios: list[ValidatedSuiteScenarioResult] = []
    seen: set[str] = set()
    for index, raw_entry in enumerate(raw_scenarios):
        entry_name = f"suite result.scenarios[{index}]"
        if not isinstance(raw_entry, dict):
            _raise_metadata_error(
                f"{entry_name} must be an object",
                path=suite_path,
                field=f"scenarios[{index}]",
            )
        scenario = raw_entry.get("scenario")
        if not isinstance(scenario, str) or not scenario:
            _raise_metadata_error(
                f"{entry_name}.scenario must be a non-empty string",
                path=suite_path,
                field=f"scenarios[{index}].scenario",
            )
        if scenario in seen:
            _raise_metadata_error(
                f"suite result contains duplicate scenario {scenario!r}",
                path=suite_path,
                field=f"scenarios[{index}].scenario",
            )
        seen.add(scenario)

        result_file = raw_entry.get("result_file")
        result_field = f"scenarios[{index}].result_file"
        if not isinstance(result_file, str) or not result_file:
            _raise_metadata_error(
                f"{entry_name}.result_file must be a non-empty string",
                path=suite_path,
                field=result_field,
            )
        result_path = _safe_result_path(
            suite_path=suite_path,
            result_file=result_file,
            field=result_field,
        )
        if not result_path.is_file():
            raise SuiteResultError(
                "missing_result_file",
                f"result for scenario {scenario!r} does not exist: {result_path}",
                path=suite_path,
                field=result_field,
            )

        scenarios.append(
            ValidatedSuiteScenarioResult(
                scenario=scenario,
                status=_scenario_status(
                    raw_entry.get("status"),
                    f"{entry_name}.status",
                    path=suite_path,
                ),
                duration_sec=_duration(
                    raw_entry.get("duration_sec"),
                    f"{entry_name}.duration_sec",
                    path=suite_path,
                ),
                result_file=result_file,
                result_path=result_path,
            )
        )

    return ValidatedSuiteResult(
        path=suite_path,
        schema_version=version,
        status=status,
        runtime=execution.runtime,
        duration_sec=duration_sec,
        scenarios=tuple(scenarios),
        execution=execution,
    )
