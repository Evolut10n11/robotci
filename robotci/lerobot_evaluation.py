"""Bounded offline contracts and deterministic gates for LeRobot PushT trials.

Only completed, protocol-compatible CPU evaluations are eligible for a gate.
Metrics are recomputed from episodes; file summaries and wall-clock performance
never decide the verdict. Trajectory hashes identify the runner's evidence, but
this portable comparison does not open trajectories or authenticate the producer.
No simulation, ML dependency, network or hardware access is needed here.
"""

from __future__ import annotations

import json
import math
import re
from fractions import Fraction
from pathlib import Path
from typing import Any

MAX_EVALUATION_BYTES = 4 * 1024 * 1024
MAX_JSON_DEPTH = 24
MAX_JSON_NODES = 100_000
MAX_EPISODES = 1000
MAX_STEPS = 10_000
RUNTIME_PACKAGES = frozenset(
    {
        "lerobot",
        "torch",
        "torchvision",
        "diffusers",
        "gym-pusht",
        "gymnasium",
        "pymunk",
        "numpy",
        "pygame",
        "shapely",
        "opencv-python",
        "safetensors",
        "scipy",
        "scikit-image",
        "opencv-python-headless",
        "draccus",
        "einops",
    }
)
_FIXED_PROTOCOL = {
    "env_id": "gym_pusht/PushT-v0",
    "obs_type": "pixels_agent_pos",
    "device": "cpu",
    "observation_shape": [3, 96, 96],
    "deterministic_algorithms": True,
    "inference_dtype": "float32",
    "control_hz": 10,
    "seed_strategy": "per_episode_python_numpy_torch_env_v1",
    "action_transform": "observed_position_plus_scaled_policy_delta_clipped_v1",
}


class LeRobotEvaluationError(ValueError):
    """An evaluation lacks valid, complete evidence for the supported profile."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LeRobotEvaluationError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _bad_constant(value: str) -> None:
    raise LeRobotEvaluationError(f"Non-finite JSON number: {value}")


def _json_copy(data: Any) -> dict[str, Any]:
    """Reject ambiguous/non-JSON values, cycles and excessive depth before copying."""
    if type(data) is not dict:
        raise LeRobotEvaluationError("Evaluation must be a JSON object.")
    stack, nodes = [(data, 0)], 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if depth > MAX_JSON_DEPTH or nodes > MAX_JSON_NODES:
            raise LeRobotEvaluationError("Evaluation exceeds JSON depth or node limits.")
        if type(value) is dict:
            if any(type(key) is not str for key in value):
                raise LeRobotEvaluationError("JSON object keys must be strings.")
            stack.extend((item, depth + 1) for item in value.values())
        elif type(value) is list:
            stack.extend((item, depth + 1) for item in value)
        elif type(value) is float:
            if not math.isfinite(value):
                raise LeRobotEvaluationError("Non-finite JSON number in evaluation.")
        elif value is not None and type(value) not in (str, int, bool):
            raise LeRobotEvaluationError("Evaluation contains a non-JSON value.")
    try:
        raw = json.dumps(data, allow_nan=False)
        if len(raw.encode("utf-8")) > MAX_EVALUATION_BYTES:
            raise LeRobotEvaluationError(f"Evaluation exceeds {MAX_EVALUATION_BYTES} bytes.")
        return json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise LeRobotEvaluationError(str(exc)) from exc


def _object(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise LeRobotEvaluationError(f"{path} must be an object.")
    return value


def _string(value: Any, path: str) -> str:
    if type(value) is not str or not value.strip():
        raise LeRobotEvaluationError(f"{path} must be a nonempty string.")
    return value


def _integer(value: Any, path: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise LeRobotEvaluationError(f"{path} must be an integer in [{minimum}, {maximum}].")
    return value


def _number(value: Any, path: str, maximum: float | None = None) -> float:
    if type(value) not in (int, float):
        raise LeRobotEvaluationError(f"{path} must be a finite nonnegative number.")
    try:
        valid = math.isfinite(value) and value >= 0 and (maximum is None or value <= maximum)
    except OverflowError:
        valid = False
    if not valid:
        suffix = f" in [0, {maximum}]" if maximum is not None else ""
        raise LeRobotEvaluationError(f"{path} must be a finite nonnegative number{suffix}.")
    return float(value)


def _hash(value: Any, path: str, length: int = 64) -> str:
    if type(value) is not str or re.fullmatch(rf"[0-9a-fA-F]{{{length}}}", value) is None:
        raise LeRobotEvaluationError(f"{path} must be a {length}-digit hexadecimal hash.")
    return value.lower()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _validate_protocol(value: Any) -> dict[str, Any]:
    protocol = _object(value, "protocol")
    for key, expected in _FIXED_PROTOCOL.items():
        if key not in protocol or _canonical(protocol[key]) != _canonical(expected):
            raise LeRobotEvaluationError(f"protocol.{key} must be {expected!r}.")
    _integer(protocol.get("max_steps"), "protocol.max_steps", 1, MAX_STEPS)
    _integer(protocol.get("torch_threads"), "protocol.torch_threads", 1, 256)
    seeds = protocol.get("seeds")
    if type(seeds) is not list or not 1 <= len(seeds) <= MAX_EPISODES:
        raise LeRobotEvaluationError(f"protocol.seeds must contain 1 to {MAX_EPISODES} seeds.")
    for seed in seeds:
        _integer(seed, "protocol.seeds[]", 0, 2**32 - 1)
    if len(set(seeds)) != len(seeds):
        raise LeRobotEvaluationError("protocol.seeds must be unique.")
    runtime = _object(protocol.get("runtime"), "protocol.runtime")
    for key in ("python", "platform", "machine"):
        _string(runtime.get(key), f"protocol.runtime.{key}")
    versions = _object(runtime.get("versions"), "protocol.runtime.versions")
    for package in sorted(RUNTIME_PACKAGES):
        _string(versions.get(package), f"protocol.runtime.versions.{package}")
    for package, version in versions.items():
        _string(package, "protocol.runtime.versions key")
        _string(version, f"protocol.runtime.versions.{package}")
    return protocol


def _validate_policy(value: Any) -> dict[str, Any]:
    policy = _object(value, "policy")
    _string(policy.get("checkpoint_id"), "policy.checkpoint_id")
    policy["revision"] = _hash(policy.get("revision"), "policy.revision", 40)
    for key in ("config_sha256", "weights_sha256"):
        policy[key] = _hash(policy.get(key), f"policy.{key}")
    _integer(policy.get("num_inference_steps"), "policy.num_inference_steps", 1, 1000)
    policy["action_scale"] = _number(policy.get("action_scale"), "policy.action_scale", 1)
    return policy


def _validate_episode(value: Any, index: int, seed: int, max_steps: int) -> dict[str, Any]:
    path = f"episodes[{index}]"
    episode = _object(value, path)
    _integer(episode.get("seed"), f"{path}.seed", 0, 2**32 - 1)
    if episode["seed"] != seed:
        raise LeRobotEvaluationError(f"{path}.seed must match protocol.seeds in order.")
    steps = _integer(episode.get("steps"), f"{path}.steps", 1, max_steps)
    for key in ("success", "terminated", "truncated"):
        if type(episode.get(key)) is not bool:
            raise LeRobotEvaluationError(f"{path}.{key} must be boolean.")
    if not (episode["terminated"] or episode["truncated"]):
        raise LeRobotEvaluationError(f"{path} did not finish or reach the episode limit.")
    if episode["success"] != episode["terminated"]:
        raise LeRobotEvaluationError(f"{path}.success must equal terminated for PushT.")
    if not episode["terminated"] and steps != max_steps:
        raise LeRobotEvaluationError(f"{path} stopped before protocol.max_steps without success.")
    if episode["truncated"] and steps != max_steps:
        raise LeRobotEvaluationError(f"{path}.truncated requires protocol.max_steps steps.")
    for key in ("max_reward", "final_reward"):
        episode[key] = _number(episode.get(key), f"{path}.{key}", 1)
    episode["sum_reward"] = _number(episode.get("sum_reward"), f"{path}.sum_reward", steps)
    if not episode["final_reward"] <= episode["max_reward"] <= episode["sum_reward"]:
        raise LeRobotEvaluationError(f"{path} requires final_reward <= max_reward <= sum_reward.")
    if episode["success"] and episode["final_reward"] != 1.0:
        raise LeRobotEvaluationError(f"{path} successful PushT must finish with reward 1.")
    for key in ("wall_time_s", "inference_time_s"):
        episode[key] = _number(episode.get(key), f"{path}.{key}")
    if episode["inference_time_s"] > episode["wall_time_s"]:
        raise LeRobotEvaluationError(f"{path}.inference_time_s cannot exceed wall_time_s.")
    episode["trajectory_sha256"] = _hash(
        episode.get("trajectory_sha256"), f"{path}.trajectory_sha256"
    )
    return episode


def _mean_fraction(episodes: list[dict[str, Any]], key: str) -> Fraction:
    return sum((Fraction(str(episode[key])) for episode in episodes), Fraction()) / len(episodes)


def _metrics(episodes: list[dict[str, Any]]) -> dict[str, int | float]:
    count = len(episodes)
    successes = sum(episode["success"] for episode in episodes)
    result: dict[str, int | float] = {
        "episodes": count,
        "successful_episodes": successes,
        "success_rate": successes / count,
    }
    for key in ("max_reward", "final_reward", "sum_reward", "steps"):
        result[f"mean_{key}"] = float(_mean_fraction(episodes, key))
    for key in ("wall_time_s", "inference_time_s"):
        try:
            total = math.fsum(episode[key] for episode in episodes)
        except OverflowError as exc:
            raise LeRobotEvaluationError(f"Aggregate {key} exceeds finite numeric bounds.") from exc
        result[f"total_{key}"] = _number(total, f"metrics.total_{key}")
    return result


def validate_evaluation(data: Any) -> dict[str, Any]:
    """Return a detached validated result with episode-derived ``metrics``.

    INFRA_ERROR, partial runs and unsupported profiles raise
    LeRobotEvaluationError. Optional JSON metadata is retained; every protocol
    field, including extensions, participates in compatibility checks.
    """
    result = _json_copy(data)
    if type(result.get("schema_version")) is not int or result["schema_version"] != 1:
        raise LeRobotEvaluationError("schema_version must be 1.")
    if result.get("artifact_type") != "lerobot_pusht_evaluation":
        raise LeRobotEvaluationError("artifact_type must be lerobot_pusht_evaluation.")
    if result.get("status") != "COMPLETED":
        raise LeRobotEvaluationError("Only COMPLETED evaluations are eligible for comparison.")
    protocol = _validate_protocol(result.get("protocol"))
    _validate_policy(result.get("policy"))
    episodes = result.get("episodes")
    if type(episodes) is not list or len(episodes) != len(protocol["seeds"]):
        raise LeRobotEvaluationError("episodes must contain exactly one result per protocol seed.")
    for index, seed in enumerate(protocol["seeds"]):
        _validate_episode(episodes[index], index, seed, protocol["max_steps"])
    result["metrics"] = _metrics(episodes)
    return result


def load_evaluation(path: str | Path) -> dict[str, Any]:
    """Read one bounded UTF-8 JSON evaluation, rejecting duplicate keys and NaN."""
    path = Path(path)
    try:
        if not path.is_file():
            raise LeRobotEvaluationError(f"Evaluation file not found: {path}")
        with path.open("rb") as source:
            raw = source.read(MAX_EVALUATION_BYTES + 1)
    except OSError as exc:
        raise LeRobotEvaluationError(f"Cannot read evaluation: {path}: {exc}") from exc
    if len(raw) > MAX_EVALUATION_BYTES:
        raise LeRobotEvaluationError(f"Evaluation exceeds {MAX_EVALUATION_BYTES} bytes: {path}")
    try:
        data = json.loads(
            raw.decode("utf-8-sig"), object_pairs_hook=_unique_object, parse_constant=_bad_constant
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise LeRobotEvaluationError(f"Invalid evaluation JSON: {path}: {exc}") from exc
    return validate_evaluation(data)


def compare_evaluations(
    baseline: Any,
    candidate: Any,
    *,
    max_success_rate_drop: float = 0.0,
    max_reward_drop: float = 0.05,
) -> dict[str, Any]:
    """Gate absolute metric drops; equality at the allowed drop passes.

    Invalid inputs/thresholds, incompatible protocols and a baseline with no
    successful episode return INFRA_ERROR. Reward decisions use exact fractions
    of the persisted decimal values, avoiding binary-rounding false regressions
    at the threshold. Timing is reported for diagnosis only.
    """
    report: dict[str, Any] = {
        "schema_version": 1,
        "artifact_type": "lerobot_pusht_comparison",
        "status": "INFRA_ERROR",
        "thresholds": {},
        "protocol": None,
        "baseline": None,
        "candidate": None,
        "checks": [],
        "findings": [],
    }
    try:
        report["thresholds"] = {
            "max_success_rate_drop": _number(max_success_rate_drop, "max_success_rate_drop", 1),
            "max_reward_drop": _number(max_reward_drop, "max_reward_drop", 1),
        }
    except LeRobotEvaluationError as exc:
        report["findings"].append({"code": "invalid_threshold", "message": str(exc)})
        return report
    validated = {}
    for name, data in (("baseline", baseline), ("candidate", candidate)):
        try:
            value = validate_evaluation(data)
        except LeRobotEvaluationError as exc:
            report["findings"].append({"code": f"invalid_{name}", "message": str(exc)})
        else:
            validated[name] = value
            report[name] = {"policy": value["policy"], "metrics": value["metrics"]}
    if len(validated) != 2:
        return report
    baseline, candidate = validated["baseline"], validated["candidate"]
    if _canonical(baseline["protocol"]) != _canonical(candidate["protocol"]):
        report["findings"].append(
            {
                "code": "incompatible_protocol",
                "message": (
                    "Baseline and candidate must have identical complete protocols and seed order."
                ),
            }
        )
        return report
    report["protocol"] = baseline["protocol"]
    if baseline["metrics"]["successful_episodes"] == 0:
        report["findings"].append(
            {
                "code": "unusable_baseline",
                "message": "Baseline must contain at least one successful episode.",
            }
        )
        return report
    count = len(baseline["episodes"])
    drops = {
        "success_rate": Fraction(
            baseline["metrics"]["successful_episodes"]
            - candidate["metrics"]["successful_episodes"],
            count,
        ),
        "mean_max_reward": (
            _mean_fraction(baseline["episodes"], "max_reward")
            - _mean_fraction(candidate["episodes"], "max_reward")
        ),
    }
    for metric, threshold in (
        ("success_rate", "max_success_rate_drop"),
        ("mean_max_reward", "max_reward_drop"),
    ):
        allowed = report["thresholds"][threshold]
        regressed = drops[metric] > Fraction(str(allowed))
        report["checks"].append(
            {
                "metric": metric,
                "baseline": baseline["metrics"][metric],
                "candidate": candidate["metrics"][metric],
                "drop": float(drops[metric]),
                "allowed_drop": allowed,
                "status": "REGRESSION" if regressed else "PASS",
            }
        )
        if regressed:
            report["findings"].append(
                {
                    "code": f"{metric}_regression",
                    "message": (
                        f"{metric} dropped by {float(drops[metric]):.12g}; allowed {allowed:.12g}."
                    ),
                }
            )
    report["status"] = "REGRESSION" if report["findings"] else "PASS"
    return report


def _markdown_text(value: Any) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    for character in ("\\", "`", "|", "[", "]", "*", "_"):
        text = text.replace(character, "\\" + character)
    return text.replace("<", "&lt;").replace(">", "&gt;")


def format_comparison_markdown(report: dict[str, Any]) -> str:
    """Render the deterministic report without filesystem or clock dependencies."""
    lines = ["# LeRobot PushT comparison", "", f"Verdict: **{report['status']}**", ""]
    if report.get("checks"):
        lines += [
            "| Metric | Baseline | Candidate | Drop | Allowed drop | Verdict |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
        for check in report["checks"]:
            lines.append(
                f"| {check['metric']} | {check['baseline']:.12g} | {check['candidate']:.12g} | "
                f"{check['drop']:.12g} | {check['allowed_drop']:.12g} | {check['status']} |"
            )
        lines.append("")
    if report.get("findings"):
        lines += ["## Findings", ""]
        lines += [
            f"- {_markdown_text(item['code'])}: {_markdown_text(item['message'])}"
            for item in report["findings"]
        ]
        lines.append("")
    if report.get("baseline") is not None and report.get("candidate") is not None:
        lines += ["## Evaluations", ""]
        for name in ("baseline", "candidate"):
            value = report[name]
            metrics, policy = value["metrics"], value["policy"]
            lines.append(
                f"- {name.capitalize()}: {_markdown_text(policy['checkpoint_id'])}, "
                f"revision {_markdown_text(policy['revision'])}; "
                f"{metrics['successful_episodes']}/{metrics['episodes']} successful episodes; "
                f"{metrics['total_wall_time_s']:.6g} s wall time."
            )
        lines.append("")
    lines += [
        "Drops are absolute metric differences; equality at the threshold passes.",
        "Wall-clock timing is diagnostic and does not affect the verdict.",
        "This gate checks simulation artifacts; trajectory files and producer authenticity "
        "are not verified by offline comparison.",
        "",
    ]
    return "\n".join(lines)
