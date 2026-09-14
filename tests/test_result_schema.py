from __future__ import annotations

from dataclasses import asdict

import pytest

from robotci.result_schema import (
    LEGACY_RESULT_SCHEMA_VERSION,
    ResultSchemaError,
    load_result,
    validate_result_payload,
)
from robotci.results import Pose2D, build_scenario_task


def _payload(
    *,
    status: str = "PASS",
    metrics: dict[str, object] | None = None,
) -> dict[str, object]:
    start = Pose2D(x=0.0, y=0.0, yaw=0.0)
    goal = Pose2D(x=1.0, y=2.0, yaw=0.0)
    return {
        "schema_version": 1,
        "scenario": "route",
        "status": status,
        "duration_sec": 2.5,
        "navigation_result": "SUCCEEDED" if status == "PASS" else status,
        "start": asdict(start),
        "goal": asdict(goal),
        "metrics": metrics
        if metrics is not None
        else {
            "path_length_m": 2.3,
            "distance_to_goal_m": 0.1,
            "stuck_events": 0,
            "feedback_samples": 12,
            "recoveries": 0,
        },
        "task": asdict(
            build_scenario_task(
                scenario="route",
                start=start,
                goal=goal,
                map_id="warehouse-v1",
            )
        ),
    }


def test_validate_current_result_returns_typed_contract() -> None:
    result = validate_result_payload(_payload())

    assert result.source_schema_version == 1
    assert result.status == "PASS"
    assert result.metrics is not None
    assert result.metrics.feedback_samples == 12
    assert result.task is not None
    assert result.provenance_complete is True


def test_legacy_v0_is_adapted_for_read_only_inspection() -> None:
    payload = _payload()
    payload.pop("schema_version")
    payload.pop("task")

    result = validate_result_payload(payload)

    assert result.source_schema_version == LEGACY_RESULT_SCHEMA_VERSION
    assert result.task is None
    assert result.provenance_complete is False


@pytest.mark.parametrize("version", [True, 1.0, "1", 2, 99])
def test_unknown_or_invalid_schema_version_is_rejected(version: object) -> None:
    payload = _payload()
    payload["schema_version"] = version

    with pytest.raises(ResultSchemaError, match="schema_version"):
        validate_result_payload(payload)


def test_infrastructure_result_can_record_missing_metrics_explicitly() -> None:
    payload = _payload(status="INFRA_ERROR")
    payload["metrics"] = None
    payload["reason_code"] = "runtime_result_invalid"

    result = validate_result_payload(payload)

    assert result.metrics is None
    assert result.status == "INFRA_ERROR"


def test_missing_metrics_requires_a_reason() -> None:
    payload = _payload(status="INFRA_ERROR")
    payload["metrics"] = None

    with pytest.raises(ResultSchemaError, match="reason_code"):
        validate_result_payload(payload)


def test_identity_strings_reject_surrounding_whitespace() -> None:
    payload = _payload()
    payload["scenario"] = " route"

    with pytest.raises(ResultSchemaError, match="surrounding whitespace"):
        validate_result_payload(payload)


def test_load_result_reports_invalid_utf8(tmp_path) -> None:
    result_path = tmp_path / "result.json"
    result_path.write_bytes(b"\xff\xfe")

    with pytest.raises(ResultSchemaError, match="valid UTF-8"):
        load_result(result_path)


def test_load_result_rejects_duplicate_json_keys(tmp_path) -> None:
    result_path = tmp_path / "result.json"
    result_path.write_text('{"scenario":"route","scenario":"other"}', encoding="utf-8")

    with pytest.raises(ResultSchemaError, match="duplicate JSON key: 'scenario'"):
        load_result(result_path)


def test_load_result_rejects_non_standard_nan_constant(tmp_path) -> None:
    result_path = tmp_path / "result.json"
    result_path.write_text('{"duration_sec":NaN}', encoding="utf-8")

    with pytest.raises(ResultSchemaError, match="non-finite JSON number: NaN"):
        load_result(result_path)
