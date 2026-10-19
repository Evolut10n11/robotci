"""Offline, bounded LeRobot metadata checks, without robot or policy execution.

Only the JSON metadata contract is checked. VALID is not a behavior verdict and
does not establish dataset integrity, joint units/order, model quality or hardware
compatibility. No LeRobot, torch, Hub, camera or serial package is imported.

Contract reference: huggingface/lerobot at
ae2b57f12223c8c5184fcd814eb63cd9ce7de203, datasets/utils.py,
utils/feature_utils.py, configs/{types,policies}.py and the Diffusion/SmolVLA
modeling modules' mandatory observation requirements.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_JSON_DEPTH = 32
MAX_FEATURES = 256
SUPPORTED_DATASET_VERSIONS = frozenset({"v2.1", "v3.0"})
SUPPORTED_POLICY_TYPES = frozenset({"act", "diffusion", "smolvla"})
_NUMERIC_DTYPES = frozenset(
    {
        "bool",
        "float16",
        "float32",
        "float64",
        "int8",
        "int16",
        "int32",
        "int64",
        "uint8",
        "uint16",
        "uint32",
        "uint64",
    }
)
_FEATURE_TYPES = frozenset({"STATE", "VISUAL", "ENV", "ACTION", "REWARD", "LANGUAGE"})
_INDEX_FEATURES = {
    "timestamp": "float32",
    "frame_index": "int64",
    "episode_index": "int64",
    "index": "int64",
    "task_index": "int64",
}


class LeRobotInspectionError(ValueError):
    """Input could not be read as bounded, unambiguous JSON metadata."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LeRobotInspectionError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _bad_constant(value: str) -> None:
    raise LeRobotInspectionError(f"Non-finite JSON number: {value}")


def _read_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        # A bounded read is required even if the file changes after stat().
        if not path.is_file():
            raise LeRobotInspectionError(f"Metadata file not found: {path}")
        with path.open("rb") as source:
            raw = source.read(MAX_METADATA_BYTES + 1)
    except OSError as exc:
        raise LeRobotInspectionError(f"Cannot read metadata: {path}: {exc}") from exc
    if len(raw) > MAX_METADATA_BYTES:
        raise LeRobotInspectionError(f"Metadata exceeds {MAX_METADATA_BYTES} bytes: {path}")
    try:
        data = json.loads(
            raw.decode("utf-8-sig"), object_pairs_hook=_unique_object, parse_constant=_bad_constant
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise LeRobotInspectionError(f"Invalid JSON metadata: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise LeRobotInspectionError(f"Metadata must be a JSON object: {path}")
    stack = [(data, 0)]
    while stack:
        value, depth = stack.pop()
        if depth > MAX_JSON_DEPTH:
            raise LeRobotInspectionError(f"Metadata exceeds depth {MAX_JSON_DEPTH}: {path}")
        if isinstance(value, float) and not math.isfinite(value):
            raise LeRobotInspectionError(f"Non-finite JSON number: {path}")
        if isinstance(value, dict):
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)
    return data, {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def _issue(
    issues: list[dict[str, str]],
    code: str,
    path: str,
    message: str,
    severity: str = "error",
) -> None:
    issues.append({"severity": severity, "code": code, "path": path, "message": message})


def _positive_int(value: Any) -> bool:
    return type(value) is int and value > 0


def _shape(value: Any) -> bool:
    return (
        isinstance(value, list)
        and 0 < len(value) <= 8
        and all(_positive_int(dimension) for dimension in value)
    )


def _dataset_features(
    features: Any,
    issues: list[dict[str, str]],
) -> dict[str, dict[str, Any]]:
    if not isinstance(features, dict) or not features or len(features) > MAX_FEATURES:
        _issue(issues, "features_invalid", "features", "Expected 1 to 256 feature definitions.")
        return {}
    valid: dict[str, dict[str, Any]] = {}
    for key, feature in sorted(features.items()):
        path = f"features.{key}"
        if not key.strip() or not isinstance(feature, dict):
            _issue(issues, "feature_invalid", path, "Expected a named feature object.")
            continue
        dtype, shape, names = feature.get("dtype"), feature.get("shape"), feature.get("names")
        if not isinstance(dtype, str) or not dtype:
            _issue(issues, "dtype_invalid", path, "A nonempty dtype string is required.")
            continue
        if dtype not in _NUMERIC_DTYPES | {"image", "video"}:
            _issue(issues, "dtype_unsupported", path, f"Unsupported dtype: {dtype}", "unsupported")
            continue
        if not _shape(shape):
            _issue(issues, "shape_invalid", path, "Shape must contain positive integer dimensions.")
            continue
        if isinstance(names, dict):
            _issue(
                issues,
                "names_layout_unsupported",
                path,
                "Legacy grouped names are not supported by this metadata profile.",
                "unsupported",
            )
            continue
        if names is not None and (
            not isinstance(names, list)
            or any(not isinstance(name, str) or not name.strip() for name in names)
        ):
            _issue(
                issues, "names_invalid", path, "Names must be null or a list of nonempty strings."
            )
            continue
        if names is not None and len(set(names)) != len(names):
            _issue(issues, "names_duplicate", path, "Feature names must not contain duplicates.")
            continue
        policy_shape = list(shape)
        if dtype in {"image", "video"}:
            if len(shape) != 3:
                _issue(
                    issues, "image_shape_invalid", path, "Visual features need three dimensions."
                )
                continue
            if names in (["height", "width", "channels"], ["height", "width", "channel"]):
                policy_shape = [shape[2], shape[0], shape[1]]
            elif names not in (["channels", "height", "width"], ["channel", "height", "width"]):
                _issue(
                    issues,
                    "image_layout_unsupported",
                    path,
                    "Explicit height/width/channel axis names are required; layout is not guessed.",
                    "unsupported",
                )
                continue
            feature_type = "VISUAL"
        else:
            if names is not None and len(shape) == 1 and len(names) != shape[0]:
                _issue(
                    issues, "names_shape_mismatch", path, "Vector names do not match its dimension."
                )
                continue
            if key == "observation.environment_state":
                feature_type = "ENV"
            elif key.startswith("observation"):
                feature_type = "STATE"
            elif key.startswith("action"):
                feature_type = "ACTION"
            else:
                feature_type = None
        valid[key] = {
            "dtype": dtype,
            "shape": shape,
            "names": names,
            "policy_shape": policy_shape,
            "policy_type": feature_type,
        }
    for key, dtype in _INDEX_FEATURES.items():
        feature = valid.get(key)
        if key not in features:
            _issue(
                issues,
                "index_feature_missing",
                f"features.{key}",
                "Required index feature missing.",
            )
        elif feature is not None and (feature["dtype"] != dtype or feature["shape"] != [1]):
            _issue(
                issues, "index_feature_invalid", f"features.{key}", f"Expected {dtype} shape [1]."
            )
    return valid


def _profile_features(policy: dict[str, Any], issues: list[dict[str, str]]) -> None:
    """Mirror supported profiles' feature requirements, without constructing a model."""
    policy_type = policy.get("type")
    inputs = policy.get("input_features")
    if isinstance(inputs, dict) and inputs and policy_type in ("diffusion", "smolvla"):
        # Both implementations consume this exact key; another STATE is not a substitute.
        state = inputs.get("observation.state")
        if not isinstance(state, dict) or state.get("type") != "STATE":
            _issue(
                issues,
                "policy_state_missing",
                "policy.input_features.observation.state",
                f"{policy_type} requires observation.state as a STATE input feature.",
            )
    if isinstance(inputs, dict) and inputs and policy_type in ("act", "diffusion"):
        definitions = [feature for feature in inputs.values() if isinstance(feature, dict)]
        images = [feature for feature in definitions if feature.get("type") == "VISUAL"]
        has_environment = any(feature.get("type") == "ENV" for feature in definitions)
        if not images and not has_environment:
            _issue(
                issues,
                "policy_observation_missing",
                "policy.input_features",
                f"{policy_type} requires at least one VISUAL or ENV input feature.",
            )
        if policy_type == "diffusion":
            image_shapes = {
                tuple(feature["shape"]) for feature in images if _shape(feature.get("shape"))
            }
            if len(image_shapes) > 1:
                _issue(
                    issues,
                    "diffusion_image_shapes_mismatch",
                    "policy.input_features",
                    "Diffusion requires all visual input features to have the same shape.",
                )
    if policy_type == "smolvla":
        empty_cameras = policy.get("empty_cameras", 0)
        if type(empty_cameras) is not int or empty_cameras < 0:
            _issue(
                issues,
                "empty_cameras_invalid",
                "policy.empty_cameras",
                "empty_cameras must be a nonnegative integer.",
            )
        elif empty_cameras:
            _issue(
                issues,
                "generated_features_unsupported",
                "policy.empty_cameras",
                "SmolVLA-generated empty camera features are outside this metadata profile.",
                "unsupported",
            )
        elif isinstance(inputs, dict) and inputs and not any(
            isinstance(feature, dict) and feature.get("type") == "VISUAL"
            for feature in inputs.values()
        ):
            _issue(
                issues,
                "policy_camera_missing",
                "policy.input_features",
                "SmolVLA requires at least one VISUAL input feature.",
            )


def _inspect_policy(
    policy: dict[str, Any],
    features: dict[str, dict[str, Any]],
    issues: list[dict[str, str]],
) -> dict[str, Any]:
    policy_type = policy.get("type")
    if not isinstance(policy_type, str) or not policy_type:
        _issue(
            issues, "policy_type_invalid", "policy.type", "A pretrained policy type is required."
        )
    elif policy_type not in SUPPORTED_POLICY_TYPES:
        _issue(
            issues,
            "policy_type_unsupported",
            "policy.type",
            f"Supported metadata profiles: {', '.join(sorted(SUPPORTED_POLICY_TYPES))}.",
            "unsupported",
        )
    checked: list[str] = []
    for direction in ("input_features", "output_features"):
        mapping = policy.get(direction)
        if mapping is None or mapping == {}:
            _issue(
                issues,
                "policy_features_unresolved",
                f"policy.{direction}",
                "Explicit pretrained features are needed; training inference is not performed.",
                "unsupported",
            )
            continue
        if not isinstance(mapping, dict) or len(mapping) > MAX_FEATURES:
            _issue(
                issues, "policy_features_invalid", f"policy.{direction}", "Expected a feature map."
            )
            continue
        for key, feature in sorted(mapping.items()):
            path = f"policy.{direction}.{key}"
            if not key.strip() or not isinstance(feature, dict):
                _issue(issues, "policy_feature_invalid", path, "Expected a named feature object.")
                continue
            kind, shape = feature.get("type"), feature.get("shape")
            if not isinstance(kind, str) or kind not in _FEATURE_TYPES:
                _issue(issues, "policy_feature_type_invalid", path, "Unknown PolicyFeature type.")
                continue
            if (direction == "input_features" and kind not in {"STATE", "VISUAL", "ENV"}) or (
                direction == "output_features" and (key != "action" or kind != "ACTION")
            ):
                _issue(
                    issues,
                    "policy_direction_invalid",
                    path,
                    "Supported profiles consume observations and produce one action feature.",
                )
                continue
            if not _shape(shape):
                _issue(
                    issues, "policy_shape_invalid", path, "Expected positive integer dimensions."
                )
                continue
            if kind in {"LANGUAGE", "REWARD"}:
                _issue(
                    issues,
                    "policy_feature_unsupported",
                    path,
                    f"{kind} preprocessing is outside this metadata profile.",
                    "unsupported",
                )
                continue
            dataset_feature = features.get(key)
            if dataset_feature is None:
                _issue(
                    issues,
                    "policy_feature_missing",
                    path,
                    "Required dataset feature is unavailable.",
                )
                continue
            if dataset_feature["policy_type"] != kind:
                _issue(
                    issues, "policy_type_mismatch", path, "Dataset and policy feature types differ."
                )
            if dataset_feature["policy_shape"] != shape:
                _issue(
                    issues,
                    "policy_shape_mismatch",
                    path,
                    f"Dataset shape {dataset_feature['policy_shape']} differs from policy {shape}.",
                )
            checked.append(key)
    output = policy.get("output_features")
    if isinstance(output, dict) and output:
        action = output.get("action")
        if not isinstance(action, dict) or action.get("type") != "ACTION":
            _issue(
                issues, "policy_action_missing", "policy.output_features", "Expected action output."
            )
    _profile_features(policy, issues)
    return {"type": policy_type, "checked_features": sorted(set(checked))}


def inspect_lerobot(
    dataset: Path,
    policy: Path | None = None,
    *,
    expected_robot_type: str | None = None,
    expected_fps: int | None = None,
) -> dict[str, Any]:
    """Inspect local metadata files; return VALID/INVALID/UNSUPPORTED for this scope.

    ``dataset`` accepts a directory or its info.json; ``policy`` accepts a
    directory or config.json. Optional expectations are explicit assertions,
    since pretrained policies do not generally declare FPS or robot_type.
    Malformed/unreadable JSON and invalid caller expectations raise
    LeRobotInspectionError. Semantic findings are returned as report issues.
    """
    if expected_robot_type is not None and (
        not isinstance(expected_robot_type, str) or not expected_robot_type.strip()
    ):
        raise LeRobotInspectionError("expected_robot_type must be a nonempty string.")
    if expected_fps is not None and not _positive_int(expected_fps):
        raise LeRobotInspectionError("expected_fps must be a positive integer.")
    dataset_path = Path(dataset)
    if dataset_path.is_dir():
        dataset_path = dataset_path / "meta" / "info.json"
    info, dataset_file = _read_json(dataset_path)
    issues: list[dict[str, str]] = []
    version = info.get("codebase_version")
    if not isinstance(version, str) or not version:
        _issue(
            issues, "version_invalid", "codebase_version", "A dataset codebase_version is required."
        )
    elif version not in SUPPORTED_DATASET_VERSIONS:
        _issue(
            issues,
            "version_unsupported",
            "codebase_version",
            "Only LeRobot Dataset v2.1 and v3.0 metadata are supported.",
            "unsupported",
        )
    fps = info.get("fps")
    if not _positive_int(fps):
        _issue(issues, "fps_invalid", "fps", "FPS must be a positive integer.")
    elif expected_fps is not None and fps != expected_fps:
        _issue(issues, "fps_mismatch", "fps", f"Expected {expected_fps}, found {fps}.")
    robot_type = info.get("robot_type")
    if robot_type is not None and (not isinstance(robot_type, str) or not robot_type.strip()):
        _issue(
            issues,
            "robot_type_invalid",
            "robot_type",
            "robot_type must be a nonempty string or null.",
        )
    if expected_robot_type is not None and robot_type != expected_robot_type:
        _issue(issues, "robot_type_mismatch", "robot_type", f"Expected {expected_robot_type}.")
    for key in ("total_episodes", "total_frames", "total_tasks"):
        value = info.get(key)
        if type(value) is not int or value < 0:
            _issue(issues, "count_invalid", key, "Expected a nonnegative integer count.")
    episodes, frames = info.get("total_episodes"), info.get("total_frames")
    if type(episodes) is int and type(frames) is int and episodes >= 0 and frames >= 0:
        if episodes > frames or (episodes == 0 and frames != 0):
            _issue(
                issues, "counts_inconsistent", "total_frames", "Episode/frame counts contradict."
            )
        elif frames == 0:
            _issue(
                issues, "dataset_empty", "total_frames", "Dataset declares no frames.", "warning"
            )
    if info.get("storage_format") is not None:
        _issue(
            issues,
            "storage_unsupported",
            "storage_format",
            "Alternative storage formats are outside this metadata profile.",
            "unsupported",
        )
    features = _dataset_features(info.get("features"), issues)
    files = {"dataset_info": dataset_file}
    policy_summary = None
    if policy is not None:
        policy_path = Path(policy)
        if policy_path.is_dir():
            policy_path = policy_path / "config.json"
        policy_data, policy_file = _read_json(policy_path)
        files["policy_config"] = policy_file
        policy_summary = _inspect_policy(policy_data, features, issues)
    severities = {issue["severity"] for issue in issues}
    status = (
        "INVALID"
        if "error" in severities
        else ("UNSUPPORTED" if "unsupported" in severities else "VALID")
    )
    return {
        "schema_version": 1,
        "scope": "metadata_only",
        "status": status,
        "dataset": {
            "codebase_version": version,
            "robot_type": robot_type,
            "fps": fps,
            "total_episodes": episodes,
            "total_frames": frames,
            "total_tasks": info.get("total_tasks"),
            "features": features,
        },
        "policy": policy_summary,
        "expectations": {"robot_type": expected_robot_type, "fps": expected_fps},
        "files": files,
        "issues": issues,
        "limitations": [
            "Only JSON declarations were read; Parquet, video, stats and weights were not checked.",
            "No policy processors, image resizing, feature renaming or inference were executed.",
            "Joint units, joint order against hardware, calibration and limits are unverified.",
            "Robot type is descriptive metadata; it does not enable a RobotCI runtime adapter.",
            "VALID is a metadata check, not a robot-behavior, safety or model-quality verdict.",
        ],
    }
