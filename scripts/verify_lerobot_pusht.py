"""Verify saved baseline/repeat/degraded CPU evidence without optional ML imports."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import stat
import struct
import sys
from pathlib import Path
from typing import Any

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from robotci.lerobot_checkpoint import PINNED_CHECKPOINT
from robotci.lerobot_evaluation import (
    LeRobotEvaluationError,
    compare_evaluations,
    format_comparison_markdown,
    load_evaluation,
)

MAX_TRACE_BYTES = 16 * 1024 * 1024
REPEAT_REWARD_ABS_TOLERANCE = 1e-12


class AcceptanceError(ValueError):
    """Missing or inconsistent trajectory evidence."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceError(message)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"Duplicate trajectory JSON key: {key}")
        result[key] = value
    return result


def _finite(value: Any, name: str) -> float:
    _require(type(value) in (int, float), f"{name} must be numeric")
    try:
        number = float(value)
    except (ValueError, OverflowError) as exc:
        raise AcceptanceError(f"{name} is not finite") from exc
    _require(math.isfinite(number), f"{name} is not finite")
    return number


def _position(value: Any, name: str) -> list[float]:
    _require(type(value) is list and len(value) == 2, f"{name} must have two coordinates")
    return [_finite(item, name) for item in value]


def _observation(value: Any) -> list[float]:
    _require(type(value) is dict, "Trajectory observation must be an object")
    digest = value.get("pixels_sha256")
    _require(
        isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
        "Trajectory observation is missing a pixel SHA-256",
    )
    return _position(value.get("agent_pos"), "observation.agent_pos")


def _trace(path: Path, episode: dict, action_scale: float) -> dict:
    try:
        info = path.lstat()
        _require(stat.S_ISREG(info.st_mode), f"Trajectory must be a regular file: {path.name}")
        _require(info.st_size <= MAX_TRACE_BYTES, f"Trajectory exceeds size limit: {path.name}")
        with path.open("rb") as source:
            raw = source.read(MAX_TRACE_BYTES + 1)
        _require(len(raw) <= MAX_TRACE_BYTES, f"Trajectory exceeds size limit: {path.name}")
    except OSError as exc:
        raise AcceptanceError(f"Cannot read trajectory {path.name}: {exc}") from exc
    _require(
        hashlib.sha256(raw).hexdigest() == episode["trajectory_sha256"],
        f"Trajectory SHA-256 mismatch: {path.name}",
    )
    try:
        trace = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise AcceptanceError(f"Invalid trajectory JSON: {path.name}: {exc}") from exc
    _require(type(trace) is dict, "Trajectory must be a JSON object")
    _require(type(trace.get("schema_version")) is int and trace["schema_version"] == 1,
             "Unsupported trajectory schema")
    _require(trace.get("artifact_type") == "lerobot_pusht_trajectory", "Wrong trajectory type")
    _require(type(trace.get("seed")) is int and trace["seed"] == episode["seed"],
             "Trajectory seed differs from episode")
    rows = trace.get("steps")
    _require(type(rows) is list and len(rows) == episode["steps"],
             "Trajectory step count differs from episode")
    previous = _observation(trace.get("initial_observation"))
    rewards: list[float] = []
    for index, row in enumerate(rows, 1):
        _require(type(row) is dict, "Trajectory step must be an object")
        _require(type(row.get("step")) is int and row["step"] == index,
                 "Trajectory step order is inconsistent")
        position = _position(row.get("agent_pos"), "step.agent_pos")
        _require(position == previous, "Trajectory observation continuity is broken")
        prediction = _position(row.get("policy_action"), "step.policy_action")
        action = _position(row.get("action"), "step.action")
        expected = [
            struct.unpack("<f", struct.pack("<f", min(512.0, max(
                0.0, pos + action_scale * (target - pos),
            ))))[0]
            for pos, target in zip(position, prediction, strict=True)
        ]
        _require(action == expected, "Recorded action does not match the declared action scale")
        reward = _finite(row.get("reward"), "step.reward")
        _require(0 <= reward <= 1, "Trajectory reward must be in [0, 1]")
        rewards.append(reward)
        for key in ("success", "terminated", "truncated"):
            _require(type(row.get(key)) is bool, f"step.{key} must be boolean")
        _require(row["success"] == row["terminated"], "Trajectory success/termination disagree")
        if row["success"]:
            _require(reward == 1.0, "Successful trajectory step must have reward 1")
        if index < len(rows):
            _require(not row["terminated"] and not row["truncated"],
                     "Trajectory continues after a terminal step")
        else:
            for key in ("success", "terminated", "truncated"):
                _require(row[key] == episode[key], f"Trajectory final {key} differs from episode")
        previous = _observation(row.get("observation"))
    _require(max(rewards) == episode["max_reward"], "Trajectory maximum reward differs")
    _require(rewards[-1] == episode["final_reward"], "Trajectory final reward differs")
    _require(math.isclose(math.fsum(rewards), episode["sum_reward"], rel_tol=0, abs_tol=1e-12),
             "Trajectory reward sum differs")
    return trace


def _verified_run(directory: Path) -> tuple[dict, dict]:
    result_path = directory / "result.json"
    result = load_evaluation(result_path)
    for episode in result["episodes"]:
        _trace(directory / f"episode-{episode['seed']}.json", episode,
               result["policy"]["action_scale"])
    return result, {
        "directory": str(directory.resolve()),
        "result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
        "verified_trajectories": len(result["episodes"]),
        "metrics": result["metrics"],
    }


def _repeat_evidence(baseline_dir: Path, unchanged_dir: Path, baseline: dict, unchanged: dict):
    _require(baseline["protocol"] == unchanged["protocol"], "Repeated protocols differ")
    assessment = {
        "reward_abs_tolerance": REPEAT_REWARD_ABS_TOLERANCE,
        "reward_rel_tolerance": 0.0, "max_reward_abs_delta": 0.0, "seeds": [],
    }
    for first, second in zip(baseline["episodes"], unchanged["episodes"], strict=True):
        left = _trace(baseline_dir / f"episode-{first['seed']}.json", first, 1.0)
        right = _trace(unchanged_dir / f"episode-{second['seed']}.json", second, 1.0)
        fields_equal = (
            left["initial_observation"] == right["initial_observation"]
            and len(left["steps"]) == len(right["steps"])
        )
        max_delta = 0.0
        for a, b in zip(left["steps"], right["steps"], strict=False):
            fields_equal = fields_equal and all(a[key] == b[key] for key in (
                "step", "agent_pos", "policy_action", "action", "observation",
                "success", "terminated", "truncated",
            ))
            max_delta = max(max_delta, abs(a["reward"] - b["reward"]))
        within_tolerance = max_delta <= REPEAT_REWARD_ABS_TOLERANCE
        assessment["seeds"].append({
            "seed": first["seed"],
            "byte_identical": first["trajectory_sha256"] == second["trajectory_sha256"],
            "non_reward_fields_identical": fields_equal,
            "max_reward_abs_delta": max_delta, "within_reward_tolerance": within_tolerance,
            "passed": fields_equal and within_tolerance,
        })
        assessment["max_reward_abs_delta"] = max(assessment["max_reward_abs_delta"], max_delta)
    return assessment


def verify_acceptance(baseline: Path, unchanged: Path, degraded: Path) -> dict:
    """Require real-run evidence invariants, stable repeats and an effective negative control."""
    report: dict = {
        "schema_version": 1, "artifact_type": "lerobot_pusht_acceptance",
        "status": "INFRA_ERROR", "runs": {}, "comparisons": {}, "findings": [],
    }
    try:
        results = {}
        for name, directory in (
            ("baseline", baseline), ("unchanged", unchanged), ("degraded", degraded),
        ):
            results[name], report["runs"][name] = _verified_run(Path(directory))
        base_policy = results["baseline"]["policy"]
        expected_provenance = {
            "checkpoint_id": PINNED_CHECKPOINT["source"]["repo_id"],
            "revision": PINNED_CHECKPOINT["source"]["revision"],
            "config_sha256": PINNED_CHECKPOINT["files"]["config.json"]["sha256"],
            "weights_sha256": PINNED_CHECKPOINT["files"]["model.safetensors"]["sha256"],
        }
        _require(all(base_policy.get(key) == value for key, value in expected_provenance.items()),
                 "Baseline provenance differs from the pinned official checkpoint")
        _require(base_policy["action_scale"] == 1, "Baseline must use the unmodified policy")
        _require(base_policy == results["unchanged"]["policy"],
                 "Repeat policy differs from baseline")
        _require({**base_policy, "action_scale": 0.0} == results["degraded"]["policy"],
                 "Degraded control must change only action_scale to zero")
        for name in ("unchanged", "degraded"):
            report["comparisons"][name] = compare_evaluations(results["baseline"], results[name])
        for name, expected in (("unchanged", "PASS"), ("degraded", "REGRESSION")):
            actual = report["comparisons"][name]["status"]
            if actual != expected:
                report["findings"].append({
                    "code": f"unexpected_{name}_gate",
                    "message": f"Expected {expected}, received {actual}",
                })
        report["repeatability"] = _repeat_evidence(
            Path(baseline), Path(unchanged), results["baseline"], results["unchanged"],
        )
        if not all(item["passed"] for item in report["repeatability"]["seeds"]):
            report["findings"].append({
                "code": "unstable_repeat",
                "message": "Repeated non-reward fields differ or per-step rewards exceed 1e-12",
            })
        report["protocol"] = results["baseline"]["protocol"]
        report["status"] = "FAIL" if report["findings"] else "PASS"
    except (AcceptanceError, LeRobotEvaluationError, OSError) as exc:
        report["findings"].append({"code": "invalid_evidence", "message": str(exc)})
    return report


def _markdown(report: dict) -> str:
    lines = ["# LeRobot PushT acceptance", "", f"Verdict: **{report['status']}**", ""]
    lines += ["| Run | Verified trajectories | Success rate | Mean max reward |",
              "| --- | ---: | ---: | ---: |"]
    for name, run in report["runs"].items():
        metrics = run["metrics"]
        lines.append(
            f"| {name} | {run['verified_trajectories']} | {metrics['success_rate']:.6f} | "
            f"{metrics['mean_max_reward']:.6f} |"
        )
    lines += ["", "Checks include all trajectory SHA-256 values, action scaling, step order,",
              "terminal flags, episode metrics, repeated traces and expected comparison gates.", ""]
    if report.get("repeatability"):
        repeat = report["repeatability"]
        lines += ["## Repeated-run evidence", "",
                  "Actions, positions, pixel hashes and flags must match exactly.",
                  "Only per-step rewards allow absolute error 1e-12; relative tolerance is zero.",
                  "Original trajectory hashes are verified individually and remain unchanged.", "",
                  "| Seed | Bytes identical | Other fields identical | Max reward difference |",
                  "| ---: | --- | --- | ---: |"]
        for item in repeat["seeds"]:
            lines.append(
                f"| {item['seed']} | {item['byte_identical']} | "
                f"{item['non_reward_fields_identical']} | {item['max_reward_abs_delta']:.16g} |"
            )
        lines.append("")
    if report["findings"]:
        lines += ["## Findings", ""]
        for item in report["findings"]:
            message = item["message"].replace("\n", " ").replace("\r", " ")
            lines.append(f"- {item['code']}: {message}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("baseline", "unchanged", "degraded", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        args.output.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        print(json.dumps({"status": "INFRA_ERROR", "error": str(exc)}))
        return 2
    report = verify_acceptance(args.baseline, args.unchanged, args.degraded)
    try:
        for name, comparison in report["comparisons"].items():
            (args.output / f"{name}-comparison.json").write_text(
                json.dumps(comparison, indent=2, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            (args.output / f"{name}-comparison.md").write_text(
                format_comparison_markdown(comparison), encoding="utf-8",
            )
        (args.output / "acceptance.md").write_text(_markdown(report), encoding="utf-8")
        # Publish the overall JSON report last so a failed write cannot imply acceptance.
        (args.output / "acceptance.json").write_text(
            json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8",
        )
    except OSError as exc:
        print(json.dumps({"status": "INFRA_ERROR", "error": str(exc)}))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
