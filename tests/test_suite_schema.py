from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from robotci.result_schema import load_result
from robotci.results import Pose2D, build_scenario_task
from robotci.suite_schema import (
    SuiteResultError,
    ValidatedSuiteResult,
    ValidatedSuiteScenarioResult,
    load_suite_result,
)

FIXTURE = Path(__file__).parent / "fixtures" / "gate-suite" / "pass"


def _copy_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "suite"
    shutil.copytree(FIXTURE, root)
    return root / "suite-result.json"


def _rewrite_suite(path: Path, update: Callable[[dict[str, Any]], None]) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    update(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_loads_valid_suite_as_typed_result(tmp_path: Path) -> None:
    suite_path = _copy_fixture(tmp_path)

    suite = load_suite_result(suite_path)

    assert isinstance(suite, ValidatedSuiteResult)
    assert suite.path == suite_path.resolve()
    assert suite.schema_version == 1
    assert suite.status == "PASS"
    assert suite.runtime == "native"
    assert suite.duration_sec == 10.5
    assert len(suite.scenarios) == 1
    assert isinstance(suite.scenarios[0], ValidatedSuiteScenarioResult)
    assert suite.scenarios[0].scenario == "route"
    assert suite.scenarios[0].result_file == "results/route.json"
    assert suite.scenarios[0].result_path == (suite_path.parent / "results/route.json").resolve()
    assert suite.scenarios[0].result == load_result(suite.scenarios[0].result_path)


def test_rejects_unsupported_schema_version(tmp_path: Path) -> None:
    suite_path = _copy_fixture(tmp_path)
    _rewrite_suite(suite_path, lambda payload: payload.__setitem__("schema_version", 2))

    with pytest.raises(SuiteResultError, match="unsupported suite result.schema_version") as error:
        load_suite_result(suite_path)

    assert error.value.code == "unsupported_schema_version"
    assert error.value.field == "schema_version"


def test_rejects_missing_scenario_result(tmp_path: Path) -> None:
    suite_path = _copy_fixture(tmp_path)
    (suite_path.parent / "results/route.json").unlink()

    with pytest.raises(SuiteResultError, match="does not exist") as error:
        load_suite_result(suite_path)

    assert error.value.code == "missing_result_file"
    assert error.value.field == "scenarios[0].result_file"


def test_rejects_malformed_execution_metadata(tmp_path: Path) -> None:
    suite_path = _copy_fixture(tmp_path)

    def corrupt_environment(payload: dict[str, object]) -> None:
        execution = payload["execution"]
        assert isinstance(execution, dict)
        environment = execution["environment"]
        assert isinstance(environment, dict)
        environment["python_version"] = []

    _rewrite_suite(suite_path, corrupt_environment)

    with pytest.raises(SuiteResultError, match="python_version") as error:
        load_suite_result(suite_path)

    assert error.value.code == "invalid_metadata"
    assert error.value.field == "execution"


def test_rejects_result_path_traversal(tmp_path: Path) -> None:
    suite_path = _copy_fixture(tmp_path)
    _rewrite_suite(
        suite_path,
        lambda payload: payload["scenarios"][0].__setitem__(
            "result_file", "../outside.json"
        ),
    )

    with pytest.raises(SuiteResultError, match="unsafe result_file path") as error:
        load_suite_result(suite_path)

    assert error.value.code == "unsafe_result_path"


def test_rejects_absolute_result_path(tmp_path: Path) -> None:
    suite_path = _copy_fixture(tmp_path)
    absolute_result = (tmp_path / "outside.json").resolve()
    shutil.copy2(suite_path.parent / "results/route.json", absolute_result)
    _rewrite_suite(
        suite_path,
        lambda payload: payload["scenarios"][0].__setitem__(
            "result_file", str(absolute_result)
        ),
    )

    with pytest.raises(SuiteResultError, match="unsafe result_file path") as error:
        load_suite_result(suite_path)

    assert error.value.code == "unsafe_result_path"


def test_rejects_result_outside_suite_results_directory(tmp_path: Path) -> None:
    suite_path = _copy_fixture(tmp_path)
    adjacent_result = suite_path.parent / "route.json"
    shutil.copy2(suite_path.parent / "results/route.json", adjacent_result)
    _rewrite_suite(
        suite_path,
        lambda payload: payload["scenarios"][0].__setitem__(
            "result_file", "route.json"
        ),
    )

    with pytest.raises(SuiteResultError, match="escapes suite results directory") as error:
        load_suite_result(suite_path)

    assert error.value.code == "unsafe_result_path"


def test_existing_suite_reference_uses_existing_scenario_reader() -> None:
    suite = load_suite_result(FIXTURE / "suite-result.json")

    scenario = load_result(suite.scenarios[0].result_path)

    assert scenario.scenario == suite.scenarios[0].scenario == "route"
    assert scenario.status == suite.scenarios[0].status == "PASS"


@pytest.mark.parametrize(
    "field,value",
    [("scenario", "another-route"), ("status", "FAIL"), ("duration_sec", 999.0)],
)
def test_rejects_suite_entry_that_disagrees_with_result(
    tmp_path: Path, field: str, value: object,
) -> None:
    suite_path = _copy_fixture(tmp_path)

    def change_entry(payload: dict[str, Any]) -> None:
        payload["scenarios"][0][field] = value
        if field == "status":
            payload["status"] = value

    _rewrite_suite(suite_path, change_entry)

    with pytest.raises(SuiteResultError) as error:
        load_suite_result(suite_path)

    assert error.value.code == "inconsistent_result"
    assert error.value.path == suite_path.resolve()
    assert error.value.field == f"scenarios[0].{field}"


@pytest.mark.parametrize("contents", [b"{broken", b"\xff", b'{"schema_version":99}'])
def test_invalid_referenced_result_has_structured_suite_error(
    tmp_path: Path, contents: bytes,
) -> None:
    suite_path = _copy_fixture(tmp_path)
    (suite_path.parent / "results/route.json").write_bytes(contents)

    with pytest.raises(SuiteResultError) as error:
        load_suite_result(suite_path)

    assert error.value.code == "invalid_result"
    assert error.value.path == suite_path.resolve()
    assert error.value.field == "scenarios[0].result_file"


@pytest.mark.parametrize(
    "duration,offset,accepted",
    [(10.5, 0.001, True), (10.5, 0.003, False), (100_000_000.0, 0.01, False)],
)
def test_entry_duration_tolerance_is_absolute_and_does_not_scale_with_duration(
    tmp_path: Path, duration: float, offset: float, accepted: bool,
) -> None:
    suite_path = _copy_fixture(tmp_path)
    result_path = suite_path.parent / "results/route.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["duration_sec"] = duration
    result_path.write_text(json.dumps(result), encoding="utf-8")
    _rewrite_suite(
        suite_path,
        lambda payload: payload["scenarios"][0].__setitem__("duration_sec", duration + offset),
    )

    if accepted:
        assert load_suite_result(suite_path).scenarios[0].result.duration_sec == duration
    else:
        with pytest.raises(SuiteResultError) as error:
            load_suite_result(suite_path)
        assert error.value.code == "inconsistent_result"
        assert error.value.field == "scenarios[0].duration_sec"


@pytest.mark.parametrize("status", ["FAIL", "TIMEOUT", "INFRA_ERROR"])
def test_consistent_non_pass_results_remain_readable(tmp_path: Path, status: str) -> None:
    suite_path = _copy_fixture(tmp_path)
    result_path = suite_path.parent / "results/route.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result.update(status=status, navigation_result="ABORTED", reason_code="navigation_aborted")
    result_path.write_text(json.dumps(result), encoding="utf-8")

    def change_status(payload: dict[str, Any]) -> None:
        payload["status"] = status
        payload["scenarios"][0]["status"] = status

    _rewrite_suite(suite_path, change_status)

    suite = load_suite_result(suite_path)
    assert suite.status == suite.scenarios[0].result.status == status


@pytest.mark.parametrize("version", [0, 1])
def test_consistent_legacy_results_remain_readable(tmp_path: Path, version: int) -> None:
    suite_path = _copy_fixture(tmp_path)
    result_path = suite_path.parent / "results/route.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["schema_version"] = version
    result.pop("telemetry_quality")
    result.pop("evidence_policy")
    if version == 0:
        result.pop("task")
    result_path.write_text(json.dumps(result), encoding="utf-8")

    loaded = load_suite_result(suite_path).scenarios[0].result
    assert loaded.source_schema_version == version
    assert loaded.evidence_complete is False


@pytest.mark.parametrize("field", ["suite", "entry"])
@pytest.mark.parametrize("value", [[], {}])
def test_malformed_status_is_a_structured_error(
    tmp_path: Path, field: str, value: object,
) -> None:
    suite_path = _copy_fixture(tmp_path)

    def change_status(payload: dict[str, Any]) -> None:
        target = payload if field == "suite" else payload["scenarios"][0]
        target["status"] = value

    _rewrite_suite(suite_path, change_status)

    with pytest.raises(SuiteResultError) as error:
        load_suite_result(suite_path)
    assert error.value.code == "invalid_metadata"


def test_suite_status_cannot_contradict_consistent_scenario_results(tmp_path: Path) -> None:
    suite_path = _copy_fixture(tmp_path)
    _rewrite_suite(suite_path, lambda payload: payload.__setitem__("status", "FAIL"))

    with pytest.raises(SuiteResultError, match="status does not match scenario statuses") as error:
        load_suite_result(suite_path)

    assert error.value.code == "invalid_metadata"
    assert error.value.field == "status"


def test_suite_wall_time_is_independent_from_scenario_durations(tmp_path: Path) -> None:
    suite_path = _copy_fixture(tmp_path)
    _rewrite_suite(suite_path, lambda payload: payload.__setitem__("duration_sec", 42.0))

    suite = load_suite_result(suite_path)

    assert suite.duration_sec == 42.0
    assert suite.scenarios[0].result.duration_sec == 10.5


@pytest.mark.parametrize(
    "statuses,expected",
    [
        (("PASS", "PASS"), "PASS"),
        (("PASS", "FAIL"), "FAIL"),
        (("TIMEOUT", "FAIL"), "TIMEOUT"),
        (("INFRA_ERROR", "TIMEOUT"), "INFRA_ERROR"),
    ],
)
def test_suite_status_uses_runner_failure_priority(
    tmp_path: Path, statuses: tuple[str, str], expected: str,
) -> None:
    suite_path = _copy_fixture(tmp_path)
    template = json.loads((suite_path.parent / "results/route.json").read_text(encoding="utf-8"))
    payload = json.loads(suite_path.read_text(encoding="utf-8"))
    entries = []
    for index, status in enumerate(statuses):
        name = f"route-{index}"
        result = {
            **template,
            "scenario": name,
            "status": status,
            "task": asdict(build_scenario_task(
                scenario=name,
                start=Pose2D(**template["start"]),
                goal=Pose2D(**template["goal"]),
                map_id=template["task"]["map_id"],
            )),
        }
        if status != "PASS":
            result.update(navigation_result="ABORTED", reason_code="navigation_aborted")
        relative_path = f"results/{name}.json"
        (suite_path.parent / relative_path).write_text(json.dumps(result), encoding="utf-8")
        entries.append({
            "scenario": name,
            "status": status,
            "duration_sec": result["duration_sec"],
            "result_file": relative_path,
        })
    payload.update(status=expected, scenarios=entries)
    suite_path.write_text(json.dumps(payload), encoding="utf-8")

    assert load_suite_result(suite_path).status == expected

    payload["status"] = "INFRA_ERROR" if expected == "PASS" else "PASS"
    suite_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SuiteResultError, match="status does not match scenario statuses"):
        load_suite_result(suite_path)
