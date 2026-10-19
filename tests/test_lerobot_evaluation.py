"""Synthetic artifacts exercise the contract; they are not simulator evidence."""

from __future__ import annotations

import builtins
import importlib.util
import json
import socket
from copy import deepcopy

import pytest

import robotci.lerobot_evaluation as evaluation
from robotci.lerobot_evaluation import (
    LeRobotEvaluationError,
    compare_evaluations,
    format_comparison_markdown,
    load_evaluation,
    validate_evaluation,
)


def artifact(rewards=(1.0, 0.8), successes=(True, False)) -> dict:
    return {
        "schema_version": 1,
        "artifact_type": "lerobot_pusht_evaluation",
        "status": "COMPLETED",
        "protocol": {
            "env_id": "gym_pusht/PushT-v0",
            "obs_type": "pixels_agent_pos",
            "max_steps": 100,
            "seeds": [41, 42],
            "device": "cpu",
            "torch_threads": 1,
            "runtime": {
                "python": "3.12.10",
                "platform": "fixture-platform",
                "machine": "fixture-architecture",
                "versions": dict.fromkeys(evaluation.RUNTIME_PACKAGES, "1.0.fixture"),
            },
            "observation_shape": [3, 96, 96],
            "deterministic_algorithms": True,
            "inference_dtype": "float32",
            "control_hz": 10,
            "seed_strategy": "per_episode_python_numpy_torch_env_v1",
            "action_transform": "observed_position_plus_scaled_policy_delta_clipped_v1",
        },
        "policy": {
            "checkpoint_id": "fixture/pusht",
            "revision": "a" * 40,
            "config_sha256": "b" * 64,
            "weights_sha256": "c" * 64,
            "num_inference_steps": 10,
            "action_scale": 1.0,
        },
        "episodes": [
            {
                "seed": seed,
                "steps": 30 if success else 100,
                "success": success,
                "terminated": success,
                "truncated": not success,
                "max_reward": reward,
                "final_reward": reward,
                "sum_reward": reward * 10,
                "wall_time_s": 5.0,
                "inference_time_s": 4.0,
                "trajectory_sha256": str(index + 1) * 64,
            }
            for index, (seed, reward, success) in enumerate(
                zip((41, 42), rewards, successes, strict=True)
            )
        ],
    }


def codes(report: dict) -> set[str]:
    return {finding["code"] for finding in report["findings"]}


def test_validation_recomputes_metrics_and_does_not_mutate_caller():
    data = artifact()
    data["summary"] = {"success_rate": 0.99, "mean_max_reward": 999}
    data["metrics"] = {"successful_episodes": 10000}
    data["policy"]["weights_sha256"] = "C" * 64
    before = deepcopy(data)
    valid = validate_evaluation(data)
    assert valid["metrics"] == {
        "episodes": 2,
        "successful_episodes": 1,
        "success_rate": 0.5,
        "mean_max_reward": 0.9,
        "mean_final_reward": 0.9,
        "mean_sum_reward": 9.0,
        "mean_steps": 65.0,
        "total_wall_time_s": 10.0,
        "total_inference_time_s": 8.0,
    }
    assert valid["policy"]["weights_sha256"] == "c" * 64
    valid["protocol"]["seeds"][0] = 999
    assert data == before


def test_load_is_offline_and_does_not_require_trajectory_files(tmp_path):
    path = tmp_path / "result.json"
    path.write_text(json.dumps(artifact()), encoding="utf-8")
    raw = path.read_bytes()
    assert load_evaluation(path)["metrics"]["episodes"] == 2
    assert path.read_bytes() == raw
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("artifact_type", "navigation"),
        ("status", "INFRA_ERROR"),
        ("status", "PASS"),
    ],
)
def test_only_supported_completed_evaluations_are_eligible(field, value):
    data = artifact()
    data[field] = value
    with pytest.raises(LeRobotEvaluationError):
        validate_evaluation(data)
    assert compare_evaluations(data, artifact())["status"] == "INFRA_ERROR"


@pytest.mark.parametrize("field", [*evaluation._FIXED_PROTOCOL, "runtime", "torch_threads"])
def test_incomplete_protocol_provenance_blocks_comparison(field):
    data = artifact()
    del data["protocol"][field]
    assert codes(compare_evaluations(artifact(), data)) == {"invalid_candidate"}


@pytest.mark.parametrize("package", sorted(evaluation.RUNTIME_PACKAGES))
def test_missing_runtime_package_version_is_not_compatible(package):
    data = artifact()
    del data["protocol"]["runtime"]["versions"][package]
    with pytest.raises(LeRobotEvaluationError, match="protocol.runtime.versions"):
        validate_evaluation(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_steps", True),
        ("max_steps", 0),
        ("max_steps", 10001),
        ("torch_threads", 0),
        ("control_hz", 10.0),
        ("deterministic_algorithms", 1),
        ("device", "cuda"),
        ("inference_dtype", "float16"),
        ("seeds", []),
        ("seeds", [41, 41]),
        ("seeds", [True, 42]),
        ("seeds", [-1, 42]),
        ("seeds", [2**32, 42]),
    ],
)
def test_invalid_protocol_values_fail_closed(field, value):
    data = artifact()
    data["protocol"][field] = value
    with pytest.raises(LeRobotEvaluationError):
        validate_evaluation(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("checkpoint_id", " "),
        ("revision", "main"),
        ("config_sha256", "a" * 63),
        ("weights_sha256", "z" * 64),
        ("num_inference_steps", True),
        ("num_inference_steps", 0),
        ("action_scale", -0.1),
        ("action_scale", 1.1),
        ("action_scale", float("inf")),
    ],
)
def test_policy_provenance_and_parameters_are_validated(field, value):
    data = artifact()
    data["policy"][field] = value
    assert codes(compare_evaluations(artifact(), data)) == {"invalid_candidate"}


@pytest.mark.parametrize("change", ["missing", "extra", "duplicate", "reordered"])
def test_exact_seed_cohort_is_required(change):
    data = artifact()
    if change == "missing":
        data["episodes"].pop()
    elif change == "extra":
        data["episodes"].append(deepcopy(data["episodes"][0]))
    elif change == "duplicate":
        data["episodes"][1]["seed"] = 41
    else:
        data["episodes"].reverse()
    with pytest.raises(LeRobotEvaluationError):
        validate_evaluation(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("seed", True),
        ("steps", True),
        ("steps", 0),
        ("steps", 101),
        ("success", 1),
        ("terminated", False),
        ("truncated", 0),
        ("truncated", True),
        ("max_reward", 1.1),
        ("max_reward", 0.9),
        ("final_reward", 0.8),
        ("sum_reward", 31),
        ("sum_reward", 0.5),
        ("wall_time_s", -1),
        ("inference_time_s", 6),
        ("max_reward", float("nan")),
        ("wall_time_s", float("inf")),
        ("trajectory_sha256", "x" * 64),
    ],
)
def test_inconsistent_or_malformed_episode_is_not_a_behavior_regression(field, value):
    data = artifact()
    data["episodes"][0][field] = value
    report = compare_evaluations(artifact(), data)
    assert report["status"] == "INFRA_ERROR"
    assert codes(report) == {"invalid_candidate"}
    assert report["checks"] == []


def test_partial_failed_episode_cannot_masquerade_as_completed():
    data = artifact()
    data["episodes"][1]["steps"] = 99
    with pytest.raises(LeRobotEvaluationError, match="before protocol.max_steps"):
        validate_evaluation(data)
    data["episodes"][1]["steps"] = 100
    data["episodes"][1]["truncated"] = False
    with pytest.raises(LeRobotEvaluationError, match="did not finish"):
        validate_evaluation(data)


def test_success_on_time_limit_can_terminate_and_truncate_together():
    data = artifact()
    data["episodes"][0].update(steps=100, truncated=True)
    assert validate_evaluation(data)["metrics"]["successful_episodes"] == 1


@pytest.mark.parametrize("change", ["seed_order", "runtime", "threads", "extra", "extra_type"])
def test_valid_but_different_protocols_are_infrastructure_errors(change):
    baseline, candidate = artifact(), artifact()
    if change == "seed_order":
        candidate["protocol"]["seeds"].reverse()
        candidate["episodes"].reverse()
    elif change == "runtime":
        candidate["protocol"]["runtime"]["versions"]["torch"] = "2.99.0"
    elif change == "threads":
        candidate["protocol"]["torch_threads"] = 2
    elif change == "extra":
        candidate["protocol"]["new_runtime_setting"] = "changed"
    else:
        baseline["protocol"]["new_runtime_setting"] = True
        candidate["protocol"]["new_runtime_setting"] = 1
    report = compare_evaluations(baseline, candidate)
    assert report["status"] == "INFRA_ERROR"
    assert codes(report) == {"incompatible_protocol"}


def test_policy_and_source_identity_can_change_without_protocol_change():
    candidate = artifact()
    candidate["policy"].update(
        checkpoint_id="fixture/candidate",
        revision="d" * 40,
        config_sha256="e" * 64,
        weights_sha256="f" * 64,
        num_inference_steps=20,
        action_scale=0.0,
        source="local",
    )
    candidate["protocol"] = dict(reversed(list(candidate["protocol"].items())))
    assert compare_evaluations(artifact(), candidate)["status"] == "PASS"


def test_baseline_needs_a_success_and_cannot_be_promoted_from_fabricated_summary():
    baseline = artifact((0.8, 0.9), (False, False))
    baseline["summary"] = baseline["metrics"] = {"successful_episodes": 2, "success_rate": 1}
    report = compare_evaluations(baseline, baseline)
    assert report["status"] == "INFRA_ERROR"
    assert codes(report) == {"unusable_baseline"}


def test_real_success_loss_is_regression_even_if_summary_claims_success():
    candidate = artifact((0.8, 0.8), (False, False))
    candidate["metrics"] = {"success_rate": 1}
    report = compare_evaluations(artifact(), candidate, max_reward_drop=1)
    assert report["status"] == "REGRESSION"
    assert codes(report) == {"success_rate_regression"}
    assert report["candidate"]["metrics"]["success_rate"] == 0


def test_success_rate_drop_uses_absolute_units_and_inclusive_limit():
    candidate = artifact((0.8, 0.8), (False, False))
    report = compare_evaluations(
        artifact(), candidate, max_success_rate_drop=0.5, max_reward_drop=1
    )
    assert report["status"] == "PASS"
    assert report["checks"][0]["drop"] == 0.5
    assert (
        compare_evaluations(
            artifact(), candidate, max_success_rate_drop=0.499999999, max_reward_drop=1
        )["status"]
        == "REGRESSION"
    )


@pytest.mark.parametrize(
    "reward,expected", [(0.7, "PASS"), (0.699999999999, "REGRESSION"), (0.9, "PASS")]
)
def test_reward_threshold_avoids_binary_rounding_false_regressions(reward, expected):
    report = compare_evaluations(artifact(), artifact((1.0, reward)), max_reward_drop=0.05)
    assert report["status"] == expected
    if expected == "REGRESSION":
        assert codes(report) == {"mean_max_reward_regression"}
    if reward == 0.7:
        assert report["checks"][1]["drop"] == 0.05


def test_both_metrics_gate_and_wall_clock_does_not():
    candidate = artifact((0.1, 0.1), (False, False))
    assert codes(compare_evaluations(artifact(), candidate)) == {
        "success_rate_regression",
        "mean_max_reward_regression",
    }
    unchanged = artifact()
    for episode in unchanged["episodes"]:
        episode.update(wall_time_s=5000, inference_time_s=4000)
    report = compare_evaluations(artifact(), unchanged)
    assert report["status"] == "PASS"
    assert report["candidate"]["metrics"]["total_wall_time_s"] == 10000


@pytest.mark.parametrize("value", [True, -0.1, 1.1, float("nan"), float("inf"), "0.1"])
@pytest.mark.parametrize("field", ["max_success_rate_drop", "max_reward_drop"])
def test_invalid_threshold_is_an_infrastructure_error(field, value):
    report = compare_evaluations(artifact(), artifact(), **{field: value})
    assert report["status"] == "INFRA_ERROR"
    assert codes(report) == {"invalid_threshold"}
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize(
    "raw",
    [
        "{",
        "[]",
        '{"x":1,"x":2}',
        '{"nested":{"x":1,"x":2}}',
        '{"x":NaN}',
        '{"x":Infinity}',
        '{"x":1e9999}',
    ],
)
def test_malformed_or_ambiguous_json_cannot_load(tmp_path, raw):
    path = tmp_path / "result.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(LeRobotEvaluationError):
        load_evaluation(path)


def test_bounded_reads_depth_and_utf8(tmp_path, monkeypatch):
    path = tmp_path / "result.json"
    with pytest.raises(LeRobotEvaluationError, match="not found"):
        load_evaluation(path)
    monkeypatch.setattr(evaluation, "MAX_EVALUATION_BYTES", 32)
    path.write_text(" " * 33, encoding="utf-8")
    with pytest.raises(LeRobotEvaluationError, match="exceeds"):
        load_evaluation(path)
    monkeypatch.setattr(evaluation, "MAX_EVALUATION_BYTES", 4096)
    path.write_text('{"nested":' * 26 + "0" + "}" * 26, encoding="utf-8")
    with pytest.raises(LeRobotEvaluationError, match="depth"):
        load_evaluation(path)
    path.write_bytes(b"\xff")
    with pytest.raises(LeRobotEvaluationError, match="Invalid evaluation JSON"):
        load_evaluation(path)


@pytest.mark.parametrize("value", [float("nan"), {1: "key"}, (1, 2), object()])
def test_invalid_extra_metadata_does_not_bypass_validation(value):
    data = artifact()
    data["uninterpreted_metadata"] = value
    assert compare_evaluations(data, artifact())["status"] == "INFRA_ERROR"


def test_cyclic_json_and_overflowing_aggregate_fail_closed():
    data = artifact()
    data["cycle"] = data
    with pytest.raises(LeRobotEvaluationError, match="depth"):
        validate_evaluation(data)
    data = artifact()
    for episode in data["episodes"]:
        episode["wall_time_s"] = 1e308
    with pytest.raises(LeRobotEvaluationError, match="Aggregate wall_time_s"):
        validate_evaluation(data)


def test_report_and_markdown_are_repeatable_and_render_errors():
    baseline, candidate = artifact(), artifact((1.0, 0.2))
    first = compare_evaluations(baseline, candidate)
    second = compare_evaluations(deepcopy(baseline), deepcopy(candidate))
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    markdown = format_comparison_markdown(first)
    assert markdown == format_comparison_markdown(second)
    assert "Verdict: **REGRESSION**" in markdown
    assert "mean_max_reward" in markdown
    assert "Wall-clock timing is diagnostic" in markdown
    assert "INFRA_ERROR" in format_comparison_markdown(
        {"status": "INFRA_ERROR", "findings": [{"code": "read_error", "message": "No file"}]}
    )


def test_markdown_escapes_untrusted_policy_names():
    candidate = artifact()
    candidate["policy"]["checkpoint_id"] = "malicious\n<img src=x>|[link](https://example.org)"
    markdown = format_comparison_markdown(compare_evaluations(artifact(), candidate))
    assert "<img" not in markdown
    assert "malicious\n" not in markdown
    assert "\\|\\[link\\]" in markdown


def test_optional_runtime_packages_and_network_are_never_used(tmp_path, monkeypatch):
    path = tmp_path / "result.json"
    path.write_text(json.dumps(artifact()), encoding="utf-8")
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        assert name.split(".")[0] not in {
            "torch",
            "lerobot",
            "huggingface_hub",
            "numpy",
            "gymnasium",
            "gym_pusht",
        }
        return original_import(name, *args, **kwargs)

    def deny_network(*args, **kwargs):
        pytest.fail("Offline evaluation attempted network access")

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(socket, "socket", deny_network)
    spec = importlib.util.spec_from_file_location(
        "isolated_lerobot_evaluation", evaluation.__file__
    )
    isolated = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(isolated)
    result = isolated.load_evaluation(path)
    assert isolated.compare_evaluations(result, result)["status"] == "PASS"
