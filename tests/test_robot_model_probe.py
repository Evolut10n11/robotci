"""Policy checks only; real physics is executed by the optional experiment workflow."""
import runpy
from pathlib import Path

import pytest

probe = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "experiments" / "robot_models" / "probe.py")
)


def metrics(**changes):
    result = {
        "engine_valid": True, "min_base_height_ratio": 0.95,
        "max_base_tilt_deg": 5.0, "joint_rmse_rad": 0.02,
        "max_joint_limit_violation_rad": 0.0,
    }
    result.update(changes)
    return result


@pytest.mark.parametrize("field,value", [
    ("engine_valid", False), ("min_base_height_ratio", 0.3),
    ("max_base_tilt_deg", 90.0), ("joint_rmse_rad", 0.3),
    ("max_joint_limit_violation_rad", 0.2),
])
def test_bad_baseline_cannot_claim_a_model_regression(field, value):
    assert probe["compare"](metrics(**{field: value}), metrics(), True) == "BASELINE_NOT_QUALIFIED"


def test_nonrepeatable_baseline_is_not_qualified():
    assert probe["compare"](metrics(), metrics(), False) == "BASELINE_NOT_QUALIFIED"


def test_real_candidate_failure_and_numerical_error_remain_distinct():
    assert probe["compare"](metrics(), metrics(min_base_height_ratio=0.2), True) == (
        "DETECTED_POSTURE_OR_TRACKING_LOSS"
    )
    assert probe["compare"](metrics(), metrics(engine_valid=False), True) == (
        "CANDIDATE_NUMERICAL_ERROR"
    )


def test_tracking_threshold_requires_absolute_and_relative_growth():
    assert probe["compare"](metrics(), metrics(joint_rmse_rad=0.029), True) == (
        "NO_REGRESSION_AT_SELECTED_THRESHOLDS"
    )
    assert probe["compare"](metrics(), metrics(joint_rmse_rad=0.04), True) == (
        "DETECTED_TRACKING_REGRESSION"
    )
