"""Synthetic evidence tests for the standalone verifier; never run an ML policy."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import shutil
from pathlib import Path

import pytest

from robotci.lerobot_checkpoint import PINNED_CHECKPOINT
from robotci.lerobot_evaluation import RUNTIME_PACKAGES

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_lerobot_pusht.py"
SPEC = importlib.util.spec_from_file_location("verify_lerobot_pusht", SCRIPT)
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


def _write_json(path: Path, value: dict) -> str:
    data = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _run_fixture(path: Path, degraded: bool) -> None:
    path.mkdir()
    position = [10.0, 20.0]

    def observation(pos):
        return {"agent_pos": pos, "pixels_sha256": "a" * 64}

    rows = []
    count = 3 if degraded else 2
    for step in range(1, count + 1):
        action = position if degraded else [110.0, 220.0]
        success = step == count and not degraded
        rows.append({
            "step": step, "agent_pos": position, "policy_action": [110.0, 220.0],
            "action": action, "observation": observation(action),
            "reward": 0.1 if degraded else (1.0 if success else 0.5),
            "success": success, "terminated": success,
            "truncated": degraded and step == count,
        })
        position = action
    digest = _write_json(path / "episode-1000.json", {
        "schema_version": 1, "artifact_type": "lerobot_pusht_trajectory", "seed": 1000,
        "initial_observation": observation([10.0, 20.0]), "steps": rows,
    })
    _write_json(path / "result.json", {
        "schema_version": 1, "artifact_type": "lerobot_pusht_evaluation", "status": "COMPLETED",
        "protocol": {
            "env_id": "gym_pusht/PushT-v0", "obs_type": "pixels_agent_pos", "device": "cpu",
            "observation_shape": [3, 96, 96], "deterministic_algorithms": True,
            "inference_dtype": "float32", "control_hz": 10, "max_steps": 3,
            "seed_strategy": "per_episode_python_numpy_torch_env_v1",
            "action_transform": "observed_position_plus_scaled_policy_delta_clipped_v1",
            "seeds": [1000], "torch_threads": 1,
            "runtime": {"python": "3.12", "platform": "unit-test", "machine": "unit-test",
                        "versions": dict.fromkeys(RUNTIME_PACKAGES, "unit-test")},
        },
        "policy": {
            "checkpoint_id": PINNED_CHECKPOINT["source"]["repo_id"],
            "revision": PINNED_CHECKPOINT["source"]["revision"],
            "config_sha256": PINNED_CHECKPOINT["files"]["config.json"]["sha256"],
            "weights_sha256": PINNED_CHECKPOINT["files"]["model.safetensors"]["sha256"],
            "action_scale": 0.0 if degraded else 1.0, "num_inference_steps": 10,
        },
        "episodes": [{
            "seed": 1000, "steps": count, "success": not degraded,
            "terminated": not degraded, "truncated": degraded,
            "max_reward": max(row["reward"] for row in rows), "final_reward": rows[-1]["reward"],
            "sum_reward": math.fsum(row["reward"] for row in rows),
            "wall_time_s": 1.0, "inference_time_s": 0.5, "trajectory_sha256": digest,
        }],
    })


@pytest.fixture
def evidence(tmp_path):
    baseline, unchanged, degraded = (tmp_path / name for name in ("base", "repeat", "bad"))
    _run_fixture(baseline, False)
    shutil.copytree(baseline, unchanged)
    _run_fixture(degraded, True)
    return baseline, unchanged, degraded


def _rewrite_trace(directory: Path, trace: dict) -> None:
    digest = _write_json(directory / "episode-1000.json", trace)
    result = json.loads((directory / "result.json").read_text())
    episode = result["episodes"][0]
    rewards = [row["reward"] for row in trace["steps"]]
    episode.update(trajectory_sha256=digest, max_reward=max(rewards), final_reward=rewards[-1],
                   sum_reward=math.fsum(rewards))
    _write_json(directory / "result.json", result)


def test_verifier_accepts_stable_repeat_and_detected_negative_control(evidence, tmp_path):
    report = verifier.verify_acceptance(*evidence)
    assert report["status"] == "PASS"
    assert report["comparisons"]["unchanged"]["status"] == "PASS"
    assert report["comparisons"]["degraded"]["status"] == "REGRESSION"
    assert report["repeatability"]["seeds"][0]["byte_identical"]
    output = tmp_path / "reports"
    arguments = [item for name, path in zip(
        ("baseline", "unchanged", "degraded"), evidence, strict=True,
    ) for item in (f"--{name}", str(path))]
    assert verifier.main([*arguments, "--output", str(output)]) == 0
    assert json.loads((output / "acceptance.json").read_text())["status"] == "PASS"
    assert (output / "degraded-comparison.md").is_file()


def test_corrupt_trace_bytes_fail_even_when_json_still_parses(evidence):
    path = evidence[1] / "episode-1000.json"
    path.write_bytes(path.read_bytes() + b"\n")
    report = verifier.verify_acceptance(*evidence)
    assert report["status"] == "INFRA_ERROR"
    assert "SHA-256 mismatch" in report["findings"][0]["message"]


def test_missing_trace_file_fails(evidence):
    (evidence[1] / "episode-1000.json").unlink()
    report = verifier.verify_acceptance(*evidence)
    assert report["status"] == "INFRA_ERROR"
    assert "Cannot read trajectory" in report["findings"][0]["message"]


@pytest.mark.parametrize("delta,expected", [(2**-52, "PASS"), (1e-6, "FAIL")])
def test_only_documented_reward_roundoff_is_tolerated(evidence, delta, expected):
    trace = json.loads((evidence[1] / "episode-1000.json").read_text())
    trace["steps"][0]["reward"] += delta
    _rewrite_trace(evidence[1], trace)
    report = verifier.verify_acceptance(*evidence)
    assert report["status"] == expected
    assessment = report["repeatability"]["seeds"][0]
    assert not assessment["byte_identical"]
    assert assessment["non_reward_fields_identical"]
    assert assessment["max_reward_abs_delta"] > 0


def test_changed_actions_fail_even_when_rewards_and_gates_match(evidence):
    trace = json.loads((evidence[1] / "episode-1000.json").read_text())
    first, second = trace["steps"]
    first["policy_action"] = [111.0, 220.0]
    first["action"] = [111.0, 220.0]
    first["observation"]["agent_pos"] = [111.0, 220.0]
    second["agent_pos"] = [111.0, 220.0]
    _rewrite_trace(evidence[1], trace)
    report = verifier.verify_acceptance(*evidence)
    assert report["comparisons"]["unchanged"]["status"] == "PASS"
    assert report["status"] == "FAIL"
    assert not report["repeatability"]["seeds"][0]["non_reward_fields_identical"]
