from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from robotci.result_schema import load_result
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
