"""Runner boundary checks; no LeRobot, NumPy, Torch, network, or weights required."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import robotci.lerobot_runner as runner


def _observation(position: list[float]) -> dict:
    data = json.dumps(position).encode()
    return {"agent_pos": position, "pixels": SimpleNamespace(tobytes=lambda: data)}


class FakeEnv:
    def __init__(self, max_steps: int):
        self.max_steps = max_steps
        self.closed = False
        self.actions: list[list[float]] = []

    def reset(self, *, seed: int):
        self.steps = 0
        return _observation([10.0, 20.0]), {"is_success": False}

    def step(self, action: list[float]):
        self.steps += 1
        self.actions.append(action)
        return (
            _observation(action), 0.25 * self.steps, False,
            self.steps == self.max_steps, {"is_success": False},
        )

    def close(self):
        self.closed = True


class FakeRuntime:
    def __init__(self):
        self.versions = dict.fromkeys(runner.RUNTIME_PACKAGES, "unit-test")
        self.seed_calls: list[int] = []

    @contextlib.contextmanager
    def settings(self, threads: int):
        yield

    def load_policy(self, checkpoint: Path, steps: int):
        pass

    def make_env(self, max_steps: int):
        self.env = FakeEnv(max_steps)
        return self.env

    def seed(self, seed: int):
        self.seed_calls.append(seed)

    def predict(self, observation: dict):
        return [110.0, 220.0]

    def step(self, env: FakeEnv, action: list[float]):
        return env.step(action)


@pytest.fixture
def fake_runtime(monkeypatch):
    runtime = FakeRuntime()
    monkeypatch.setattr(runner, "_CpuRuntime", lambda: runtime)
    monkeypatch.setattr("robotci.lerobot_checkpoint.verify_checkpoint", lambda path: {
        "source": {"repo_id": "lerobot/diffusion_pusht", "revision": "a" * 40},
        "files": {
            "config.json": {"sha256": "b" * 64},
            "model.safetensors": {"sha256": "c" * 64},
        },
    })
    return runtime


@pytest.mark.parametrize("scale,expected", [
    (0.0, [10.0, 20.0]), (0.5, [60.0, 120.0]), (1.0, [110.0, 220.0]),
])
def test_degradation_scales_motion_from_observed_position(scale, expected):
    runtime, env = FakeRuntime(), FakeEnv(1)
    episode, trajectory = runner._run_episode(
        runtime, env, seed=17, max_steps=1, action_scale=scale,
    )
    assert env.actions == [expected]
    assert trajectory["steps"][0]["action"] == expected
    assert runtime.seed_calls == [17]
    assert episode["truncated"] and not episode["success"]


def test_policy_action_clipped_before_real_environment_step():
    runtime, env = FakeRuntime(), FakeEnv(1)
    runtime.predict = lambda observation: [-100.0, 800.0]
    runner._run_episode(runtime, env, seed=4, max_steps=1, action_scale=1.0)
    assert env.actions == [[0.0, 512.0]]


def test_seeded_runs_save_complete_auditable_evidence(tmp_path, fake_runtime):
    output = tmp_path / "evaluation"
    result = runner.run_pusht(tmp_path / "checkpoint", output, seeds=[17, 18], max_steps=2)
    assert result["status"] == "COMPLETED"
    assert fake_runtime.seed_calls == [17, 18]
    assert fake_runtime.env.closed
    assert result == json.loads((output / "result.json").read_text())
    for episode in result["episodes"]:
        data = (output / f"episode-{episode['seed']}.json").read_bytes()
        assert hashlib.sha256(data).hexdigest() == episode["trajectory_sha256"]
        assert episode["steps"] == 2 and episode["truncated"]
        assert episode["max_reward"] == 0.5
        assert episode["sum_reward"] == 0.75
    # Wall-clock timings never enter the deterministic trajectory fingerprint.
    repeat = runner.run_pusht(
        tmp_path / "checkpoint", tmp_path / "repeat", seeds=[17, 18], max_steps=2,
    )
    assert [ep["trajectory_sha256"] for ep in result["episodes"]] == [
        ep["trajectory_sha256"] for ep in repeat["episodes"]
    ]


def test_existing_evidence_is_never_overwritten(tmp_path, fake_runtime):
    output = tmp_path / "existing"
    output.mkdir()
    evidence = output / "result.json"
    evidence.write_text("retained evidence")
    with pytest.raises(runner.LeRobotRunnerError):
        runner.run_pusht(tmp_path / "checkpoint", output, seeds=[1])
    assert evidence.read_text() == "retained evidence"


@pytest.mark.parametrize("kwargs", [
    {"seeds": []}, {"seeds": [1, 1]}, {"seeds": [True]}, {"seeds": [-1]},
    {"seeds": [2**32]}, {"seeds": list(range(1001))}, {"max_steps": 0},
    {"max_steps": 10_001}, {"num_inference_steps": 0}, {"num_inference_steps": 101},
    {"action_scale": float("nan")}, {"action_scale": -0.1}, {"action_scale": 1.1},
    {"action_scale": True}, {"torch_threads": 0}, {"torch_threads": 257},
])
def test_bad_arguments_do_not_create_evidence(tmp_path, kwargs):
    settings = {"seeds": [1], **kwargs}
    output = tmp_path / "evaluation"
    with pytest.raises(runner.LeRobotRunnerError):
        runner.run_pusht(tmp_path / "checkpoint", output, **settings)
    assert not output.exists()


def test_model_load_failure_is_infrastructure_not_bad_policy(tmp_path, fake_runtime):
    def fail(*args):
        raise RuntimeError("normalization state missing")

    fake_runtime.load_policy = fail
    result = runner.run_pusht(tmp_path / "checkpoint", tmp_path / "evaluation", seeds=[1])
    assert result["status"] == "INFRA_ERROR"
    assert result["episodes"] == []
    assert "normalization state missing" in result["error"]["message"]


def test_result_write_failure_is_a_public_runner_error(tmp_path, fake_runtime, monkeypatch):
    original = runner._atomic_json

    def fail_result(path, value):
        if path.name == "result.json":
            raise OSError("disk full")
        return original(path, value)

    monkeypatch.setattr(runner, "_atomic_json", fail_result)
    with pytest.raises(runner.LeRobotRunnerError, match="disk full"):
        runner.run_pusht(
            tmp_path / "checkpoint", tmp_path / "evaluation", seeds=[1], max_steps=1,
        )


def test_import_messages_and_environment_settings_do_not_leak(
    tmp_path, fake_runtime, monkeypatch, capsys,
):
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")

    def noisy_load(*args):
        assert runner.os.environ["HF_HUB_OFFLINE"] == "1"
        print("third-party import banner")

    fake_runtime.load_policy = noisy_load
    runner.run_pusht(tmp_path / "checkpoint", tmp_path / "evaluation", seeds=[1], max_steps=1)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "third-party import banner" in captured.err
    assert runner.os.environ["HF_HUB_OFFLINE"] == "0"


def test_partial_failure_never_becomes_completed_evaluation(tmp_path, fake_runtime):
    old_seed = fake_runtime.seed

    def fail_second(seed):
        if seed == 2:
            raise RuntimeError("simulator reset failed")
        old_seed(seed)

    fake_runtime.seed = fail_second
    result = runner.run_pusht(
        tmp_path / "checkpoint", tmp_path / "evaluation", seeds=[1, 2], max_steps=1,
    )
    assert result["status"] == "INFRA_ERROR"
    assert [ep["seed"] for ep in result["episodes"]] == [1]
    assert fake_runtime.env.closed


def test_nan_action_is_rejected_before_environment_step():
    runtime, env = FakeRuntime(), FakeEnv(1)
    runtime.predict = lambda observation: [float("nan"), 0.0]
    with pytest.raises(ValueError, match="finite"):
        runner._run_episode(runtime, env, seed=1, max_steps=1, action_scale=1.0)
    assert env.actions == []


def test_success_requires_consistent_simulator_termination():
    runtime, env = FakeRuntime(), FakeEnv(1)
    runtime.step = lambda env, action: (
        _observation(action), 1.0, False, False, {"is_success": True},
    )
    with pytest.raises(ValueError, match="disagree"):
        runner._run_episode(runtime, env, seed=1, max_steps=1, action_scale=1.0)


def test_import_does_not_load_optional_runtime(monkeypatch):
    original = importlib.import_module

    def guarded(name, package=None):
        assert name.split(".")[0] not in {
            "torch", "lerobot", "numpy", "gymnasium", "gym_pusht", "draccus",
        }
        return original(name, package)

    monkeypatch.setattr(importlib, "import_module", guarded)
    spec = importlib.util.spec_from_file_location("isolated_lerobot_runner", runner.__file__)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    assert callable(module.run_pusht)
