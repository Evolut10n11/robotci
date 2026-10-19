"""Synthetic metadata fixtures verify contracts; these are not recorded robot trials."""

from __future__ import annotations

import builtins
import hashlib
import importlib.util
import json
import socket
from copy import deepcopy
from pathlib import Path

import pytest

import robotci.lerobot_inspect as inspector
from robotci.lerobot_inspect import LeRobotInspectionError, inspect_lerobot

JOINTS = [
    "shoulder_pan.pos",
    "shoulder_lift.pos",
    "elbow_flex.pos",
    "wrist_flex.pos",
    "wrist_roll.pos",
    "gripper.pos",
]


def metadata() -> dict:
    features = {
        key: {"dtype": "float32" if key == "timestamp" else "int64", "shape": [1], "names": None}
        for key in ("timestamp", "frame_index", "episode_index", "index", "task_index")
    }
    features.update(
        {
            "observation.state": {"dtype": "float32", "shape": [6], "names": JOINTS},
            "action": {"dtype": "float32", "shape": [6], "names": JOINTS},
            "observation.images.front": {
                "dtype": "video",
                "shape": [480, 640, 3],
                "names": ["height", "width", "channels"],
            },
        }
    )
    return {
        "codebase_version": "v3.0",
        "robot_type": "so101_follower",
        "fps": 30,
        "total_episodes": 2,
        "total_frames": 60,
        "total_tasks": 1,
        "features": features,
    }


def policy_config() -> dict:
    return {
        "type": "act",
        "input_features": {
            "observation.state": {"type": "STATE", "shape": [6]},
            "observation.images.front": {"type": "VISUAL", "shape": [3, 480, 640]},
        },
        "output_features": {"action": {"type": "ACTION", "shape": [6]}},
    }


def save(tmp_path: Path, info: dict | None = None, policy: dict | None = None) -> tuple[Path, Path]:
    dataset = tmp_path / "dataset"
    (dataset / "meta").mkdir(parents=True, exist_ok=True)
    (dataset / "meta" / "info.json").write_text(json.dumps(info or metadata()), encoding="utf-8")
    model = tmp_path / "model"
    model.mkdir(exist_ok=True)
    (model / "config.json").write_text(json.dumps(policy or policy_config()), encoding="utf-8")
    return dataset, model


def codes(report: dict) -> set[str]:
    return {issue["code"] for issue in report["issues"]}


@pytest.mark.parametrize("version", ["v2.1", "v3.0"])
@pytest.mark.parametrize("policy_type", ["act", "diffusion", "smolvla"])
def test_supported_metadata_and_policy_contract(tmp_path, version, policy_type):
    info, config = metadata(), policy_config()
    info["codebase_version"], config["type"] = version, policy_type
    dataset, policy = save(tmp_path, info, config)
    raw = (dataset / "meta" / "info.json").read_bytes()
    result = inspect_lerobot(dataset, policy, expected_robot_type="so101_follower", expected_fps=30)
    assert result["status"] == "VALID"
    assert result["scope"] == "metadata_only"
    assert result["issues"] == []
    assert result["files"]["dataset_info"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["dataset"]["features"]["observation.state"]["names"] == JOINTS
    assert any("joint order" in line for line in result["limitations"])
    assert (dataset / "meta" / "info.json").read_bytes() == raw
    assert not (dataset / "data").exists()  # This is explicitly not a full dataset check.


@pytest.mark.parametrize("channel_name", ["channel", "channels"])
def test_channel_first_and_legacy_channel_axis_are_supported(tmp_path, channel_name):
    info = metadata()
    camera = info["features"]["observation.images.front"]
    camera.update(shape=[3, 480, 640], names=[channel_name, "height", "width"])
    dataset, policy = save(tmp_path, info)
    assert inspect_lerobot(dataset, policy)["status"] == "VALID"
    camera.update(shape=[480, 640, 3], names=["height", "width", channel_name])
    save(tmp_path, info)
    assert inspect_lerobot(dataset, policy)["status"] == "VALID"


@pytest.mark.parametrize("names", [None, ["x", "y", "z"], ["width", "height", "channels"]])
def test_visual_layout_is_never_guessed(tmp_path, names):
    info = metadata()
    info["features"]["observation.images.front"]["names"] = names
    dataset, _ = save(tmp_path, info)
    result = inspect_lerobot(dataset)
    assert result["status"] == "UNSUPPORTED"
    assert "image_layout_unsupported" in codes(result)


def test_mismatched_policy_shape_camera_name_and_type_block(tmp_path):
    config = policy_config()
    config["output_features"]["action"]["shape"] = [7]
    config["input_features"]["observation.images.wrist"] = {
        "type": "VISUAL",
        "shape": [3, 480, 640],
    }
    config["input_features"]["observation.state"]["type"] = "ENV"
    dataset, policy = save(tmp_path, policy=config)
    result = inspect_lerobot(dataset, policy)
    assert result["status"] == "INVALID"
    assert {"policy_shape_mismatch", "policy_feature_missing", "policy_type_mismatch"} <= codes(
        result
    )


@pytest.mark.parametrize("policy_type", ["act", "diffusion"])
def test_profile_rejects_state_only_observations(tmp_path, policy_type):
    config = policy_config()
    config["type"] = policy_type
    del config["input_features"]["observation.images.front"]
    dataset, policy = save(tmp_path, policy=config)
    result = inspect_lerobot(dataset, policy)
    assert result["status"] == "INVALID"
    assert "policy_observation_missing" in codes(result)


@pytest.mark.parametrize("state_key", [None, "observation.joints"])
def test_diffusion_requires_named_robot_state(tmp_path, state_key):
    info, config = metadata(), policy_config()
    config["type"] = "diffusion"
    dataset_state = info["features"].pop("observation.state")
    policy_state = config["input_features"].pop("observation.state")
    if state_key is not None:
        info["features"][state_key] = dataset_state
        config["input_features"][state_key] = policy_state
    dataset, policy = save(tmp_path, info, config)
    result = inspect_lerobot(dataset, policy)
    assert result["status"] == "INVALID"
    assert "policy_state_missing" in codes(result)


def test_smolvla_requires_robot_state(tmp_path):
    info, config = metadata(), policy_config()
    config["type"] = "smolvla"
    del info["features"]["observation.state"]
    del config["input_features"]["observation.state"]
    dataset, policy = save(tmp_path, info, config)
    result = inspect_lerobot(dataset, policy)
    assert result["status"] == "INVALID"
    assert "policy_state_missing" in codes(result)


def test_smolvla_requires_camera_even_with_environment_state(tmp_path):
    info, config = metadata(), policy_config()
    config["type"] = "smolvla"
    del info["features"]["observation.images.front"]
    del config["input_features"]["observation.images.front"]
    info["features"]["observation.environment_state"] = {
        "dtype": "float32", "shape": [3], "names": None,
    }
    config["input_features"]["observation.environment_state"] = {"type": "ENV", "shape": [3]}
    dataset, policy = save(tmp_path, info, config)
    result = inspect_lerobot(dataset, policy)
    assert result["status"] == "INVALID"
    assert "policy_camera_missing" in codes(result)


def test_act_supports_camera_without_robot_state(tmp_path):
    info, config = metadata(), policy_config()
    del info["features"]["observation.state"]
    del config["input_features"]["observation.state"]
    dataset, policy = save(tmp_path, info, config)
    assert inspect_lerobot(dataset, policy)["status"] == "VALID"


@pytest.mark.parametrize("policy_type", ["act", "diffusion"])
def test_profile_accepts_environment_instead_of_visual_observations(tmp_path, policy_type):
    info, config = metadata(), policy_config()
    config["type"] = policy_type
    del config["input_features"]["observation.images.front"]
    config["input_features"]["observation.environment_state"] = {"type": "ENV", "shape": [3]}
    info["features"]["observation.environment_state"] = {
        "dtype": "float32",
        "shape": [3],
        "names": ["x", "y", "angle"],
    }
    dataset, policy = save(tmp_path, info, config)
    assert inspect_lerobot(dataset, policy)["status"] == "VALID"


@pytest.mark.parametrize(
    "second_shape,expected", [([240, 320, 3], "INVALID"), ([480, 640, 3], "VALID")]
)
def test_diffusion_cameras_must_share_shape_even_when_dataset_matches(
    tmp_path, second_shape, expected
):
    info, config = metadata(), policy_config()
    config["type"] = "diffusion"
    info["features"]["observation.images.wrist"] = {
        "dtype": "video",
        "shape": second_shape,
        "names": ["height", "width", "channels"],
    }
    config["input_features"]["observation.images.wrist"] = {
        "type": "VISUAL",
        "shape": [second_shape[2], second_shape[0], second_shape[1]],
    }
    dataset, policy = save(tmp_path, info, config)
    result = inspect_lerobot(dataset, policy)
    assert result["status"] == expected
    if expected == "INVALID":
        assert "diffusion_image_shapes_mismatch" in codes(result)
        assert "policy_shape_mismatch" not in codes(result)


@pytest.mark.parametrize(
    "value,expected", [(0, "VALID"), (1, "UNSUPPORTED"), (-1, "INVALID"), (True, "INVALID")]
)
def test_smolvla_generated_camera_features_are_not_silently_ignored(tmp_path, value, expected):
    config = policy_config()
    config.update(type="smolvla", empty_cameras=value)
    dataset, policy = save(tmp_path, policy=config)
    assert inspect_lerobot(dataset, policy)["status"] == expected


def test_explicit_fps_and_robot_expectations(tmp_path):
    dataset, policy = save(tmp_path)
    result = inspect_lerobot(dataset, policy, expected_fps=50, expected_robot_type="koch_follower")
    assert result["status"] == "INVALID"
    assert {"fps_mismatch", "robot_type_mismatch"} <= codes(result)


@pytest.mark.parametrize(
    "field,value", [("fps", True), ("fps", 0), ("fps", 30.5), ("total_frames", -1)]
)
def test_invalid_numbers_fail_closed(tmp_path, field, value):
    info = metadata()
    info[field] = value
    dataset, _ = save(tmp_path, info)
    assert inspect_lerobot(dataset)["status"] == "INVALID"


@pytest.mark.parametrize("shape", [[True], [0], [-1], [6.0], [], "6", None])
def test_invalid_dimensions(tmp_path, shape):
    info = metadata()
    info["features"]["action"]["shape"] = shape
    dataset, _ = save(tmp_path, info)
    assert "shape_invalid" in codes(inspect_lerobot(dataset))


@pytest.mark.parametrize(
    "bad_names,code", [(["x"] * 6, "names_duplicate"), (["x"], "names_shape_mismatch")]
)
def test_joint_name_contract(tmp_path, bad_names, code):
    info = metadata()
    info["features"]["action"]["names"] = bad_names
    dataset, _ = save(tmp_path, info)
    assert code in codes(inspect_lerobot(dataset))


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("codebase_version", "v4.0", "version_unsupported"),
        ("storage_format", "lance", "storage_unsupported"),
    ],
)
def test_unknown_dataset_schemas_are_unsupported(tmp_path, field, value, code):
    info = metadata()
    info[field] = value
    dataset, _ = save(tmp_path, info)
    result = inspect_lerobot(dataset)
    assert result["status"] == "UNSUPPORTED"
    assert code in codes(result)


@pytest.mark.parametrize("field,value", [("type", "future_policy"), ("input_features", None)])
def test_unsupported_policy_cannot_return_valid(tmp_path, field, value):
    config = policy_config()
    config[field] = value
    dataset, policy = save(tmp_path, policy=config)
    assert inspect_lerobot(dataset, policy)["status"] == "UNSUPPORTED"


def test_legacy_grouped_names_are_explicitly_unsupported(tmp_path):
    info = metadata()
    info["features"]["action"]["names"] = {"motors": JOINTS}
    dataset, _ = save(tmp_path, info)
    result = inspect_lerobot(dataset)
    assert result["status"] == "UNSUPPORTED"
    assert "names_layout_unsupported" in codes(result)


@pytest.mark.parametrize(
    "direction,key,kind",
    [
        ("input_features", "action", "ACTION"),
        ("output_features", "observation.state", "STATE"),
        ("output_features", "alternative_action", "ACTION"),
    ],
)
def test_policy_feature_direction_is_validated(tmp_path, direction, key, kind):
    config = policy_config()
    config[direction][key] = {"type": kind, "shape": [6]}
    dataset, policy = save(tmp_path, policy=config)
    result = inspect_lerobot(dataset, policy)
    assert result["status"] == "INVALID"
    assert "policy_direction_invalid" in codes(result)


@pytest.mark.parametrize("value", [[], "bad", False, {"action": None}, {"action": []}])
def test_malformed_feature_maps_return_invalid_without_traceback(tmp_path, value):
    config = policy_config()
    config["output_features"] = value
    dataset, policy = save(tmp_path, policy=config)
    assert inspect_lerobot(dataset, policy)["status"] == "INVALID"


def test_index_feature_is_required_and_counts_consistent(tmp_path):
    info = metadata()
    del info["features"]["timestamp"]
    info["total_episodes"] = 61
    dataset, _ = save(tmp_path, info)
    assert {"index_feature_missing", "counts_inconsistent"} <= codes(inspect_lerobot(dataset))


@pytest.mark.parametrize(
    "raw",
    [
        '{"fps": 30, "fps": 50}',
        '{"nested":{"x":1,"x":2}}',
        '{"fps": NaN}',
        '{"fps": Infinity}',
        '{"fps": 1e9999}',
        "[]",
        "{",
    ],
)
def test_ambiguous_and_malformed_json_is_rejected(tmp_path, raw):
    path = tmp_path / "info.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(LeRobotInspectionError):
        inspect_lerobot(path)


def test_size_depth_and_missing_file_bounds(tmp_path, monkeypatch):
    path = tmp_path / "info.json"
    with pytest.raises(LeRobotInspectionError, match="not found"):
        inspect_lerobot(path)
    monkeypatch.setattr(inspector, "MAX_METADATA_BYTES", 32)
    path.write_text(" " * 33, encoding="utf-8")
    with pytest.raises(LeRobotInspectionError, match="exceeds"):
        inspect_lerobot(path)
    monkeypatch.setattr(inspector, "MAX_METADATA_BYTES", 4096)
    path.write_text('{"x":' * 35 + "0" + "}" * 35, encoding="utf-8")
    with pytest.raises(LeRobotInspectionError, match="depth"):
        inspect_lerobot(path)


def test_no_optional_runtime_imports_or_network(tmp_path, monkeypatch):
    dataset, policy = save(tmp_path)
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        assert name.split(".")[0] not in {"torch", "lerobot", "huggingface_hub", "serial", "numpy"}
        return original_import(name, *args, **kwargs)

    def deny_network(*args, **kwargs):
        pytest.fail("Metadata inspection attempted network access")

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(socket, "socket", deny_network)
    spec = importlib.util.spec_from_file_location("isolated_lerobot_inspect", inspector.__file__)
    isolated = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(isolated)
    assert isolated.inspect_lerobot(dataset, policy)["status"] == "VALID"


def test_caller_expectations_are_validated(tmp_path):
    dataset, _ = save(tmp_path)
    for arguments in ({"expected_fps": True}, {"expected_fps": 0}, {"expected_robot_type": ""}):
        with pytest.raises(ValueError):
            inspect_lerobot(dataset, **arguments)


def test_does_not_infer_joint_units_or_hardware_order(tmp_path):
    info = deepcopy(metadata())
    info["features"]["action"]["names"] = list(reversed(JOINTS))
    dataset, policy = save(tmp_path, info)
    result = inspect_lerobot(dataset, policy)
    # PolicyFeature has no joint names. A shape comparison cannot prove order.
    assert result["status"] == "VALID"
    assert any("Joint units, joint order" in line for line in result["limitations"])
