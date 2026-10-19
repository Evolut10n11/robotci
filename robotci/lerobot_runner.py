"""Optional, offline CPU evaluation of the pinned LeRobot Diffusion PushT policy.

Importing this module does not import an ML library, download weights, or open a
simulator. The legacy checkpoint keeps normalization in its model state; LeRobot
0.3.3 is deliberately pinned rather than silently dropping these statistics.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import json
import math
import os
import platform
import random
import struct
import sys
import tempfile
import time
from importlib import metadata
from pathlib import Path
from typing import Any

ENV_ID = "gym_pusht/PushT-v0"
OBS_TYPE = "pixels_agent_pos"
RUNTIME_PACKAGES = (
    "lerobot", "torch", "torchvision", "diffusers", "gym-pusht", "gymnasium",
    "pymunk", "numpy", "pygame", "shapely", "opencv-python", "safetensors",
    "scipy", "scikit-image", "opencv-python-headless", "draccus", "einops",
)


class LeRobotRunnerError(ValueError):
    """Invalid evaluation arguments or an output path that cannot be safely created."""


def _vector2(value: Any, name: str) -> list[float]:
    try:
        result = [float(item) for item in value]
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must contain two finite numbers") from exc
    if len(result) != 2 or not all(math.isfinite(item) for item in result):
        raise ValueError(f"{name} must contain two finite numbers")
    return result


def _observation_record(observation: dict[str, Any]) -> dict[str, Any]:
    pixels = observation["pixels"]
    return {
        "agent_pos": _vector2(observation["agent_pos"], "agent position"),
        "pixels_sha256": hashlib.sha256(pixels.tobytes()).hexdigest(),
    }


def _atomic_json(path: Path, value: dict[str, Any]) -> str:
    """Write complete JSON before making it visible, including on Windows."""
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                          allow_nan=False) + "\n").encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return hashlib.sha256(payload).hexdigest()


@contextlib.contextmanager
def _offline_environment():
    settings = {
        "HF_HUB_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1", "TRANSFORMERS_OFFLINE": "1",
        "PYGAME_HIDE_SUPPORT_PROMPT": "1", "SDL_VIDEODRIVER": "dummy",
        "SDL_AUDIODRIVER": "dummy",
    }
    previous = {key: os.environ.get(key) for key in settings}
    os.environ.update(settings)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class _CpuRuntime:
    """The only boundary at which optional ML and simulator packages are loaded."""

    def __init__(self) -> None:
        self.versions = {name: metadata.version(name) for name in RUNTIME_PACKAGES}
        if self.versions["lerobot"] != "0.3.3":
            raise RuntimeError(
                "This legacy checkpoint requires lerobot==0.3.3; install the pinned "
                "experiments/lerobot_pusht/requirements.txt in a separate environment"
            )
        if self.versions["gym-pusht"] != "0.1.5":
            raise RuntimeError("This evaluation protocol requires gym-pusht==0.1.5")
        self.np = importlib.import_module("numpy")
        self.torch = importlib.import_module("torch")
        self.gym = importlib.import_module("gymnasium")
        importlib.import_module("gym_pusht")
        self.policy: Any = None

    @contextlib.contextmanager
    def settings(self, torch_threads: int):
        torch = self.torch
        previous = (
            random.getstate(), self.np.random.get_state(), torch.get_rng_state(),
            torch.get_num_threads(), torch.are_deterministic_algorithms_enabled(),
            torch.is_deterministic_algorithms_warn_only_enabled(),
        )
        try:
            torch.set_num_threads(torch_threads)
            torch.use_deterministic_algorithms(True, warn_only=False)
            yield
        finally:
            random.setstate(previous[0])
            self.np.random.set_state(previous[1])
            torch.set_rng_state(previous[2])
            torch.set_num_threads(previous[3])
            torch.use_deterministic_algorithms(previous[4], warn_only=previous[5])

    def load_policy(self, checkpoint: Path, num_inference_steps: int) -> None:
        draccus = importlib.import_module("draccus")
        config_module = importlib.import_module(
            "lerobot.policies.diffusion.configuration_diffusion"
        )
        policy_module = importlib.import_module("lerobot.policies.diffusion.modeling_diffusion")
        payload = json.loads((checkpoint / "config.json").read_text(encoding="utf-8"))
        if payload.pop("type", None) != "diffusion":
            raise ValueError("The checkpoint must contain a Diffusion policy")
        payload.update(device="cpu", use_amp=False, num_inference_steps=num_inference_steps)
        # Avoid upstream's open NamedTemporaryFile re-read, which is unsafe on Windows.
        config = draccus.decode(config_module.DiffusionConfig, payload)
        with contextlib.redirect_stdout(sys.stderr):
            self.policy = policy_module.DiffusionPolicy.from_pretrained(
                checkpoint, config=config, local_files_only=True, strict=True,
            )
        self.policy.to(device="cpu", dtype=self.torch.float32).eval()
        normalization = {
            name: tensor for name, tensor in self.policy.state_dict().items()
            if name.startswith(("normalize_inputs.", "unnormalize_outputs."))
        }
        if not normalization or not all(
            self.torch.isfinite(tensor).all().item() for tensor in normalization.values()
        ):
            raise RuntimeError("The checkpoint did not load finite normalization statistics")

    def make_env(self, max_steps: int) -> Any:
        return self.gym.make(
            ENV_ID, obs_type=OBS_TYPE, render_mode="rgb_array",
            observation_width=96, observation_height=96, max_episode_steps=max_steps,
        )

    def seed(self, seed: int) -> None:
        random.seed(seed)
        self.np.random.seed(seed)
        self.torch.manual_seed(seed)
        self.policy.reset()

    def predict(self, observation: dict[str, Any]) -> list[float]:
        pixels = self.np.asarray(observation["pixels"])
        if pixels.shape != (96, 96, 3) or pixels.dtype != self.np.uint8:
            raise ValueError("PushT must return RGB uint8 observations of shape (96, 96, 3)")
        position = _vector2(observation["agent_pos"], "agent position")
        torch = self.torch
        batch = {
            "observation.image": (
                torch.from_numpy(pixels.copy()).permute(2, 0, 1).contiguous()
                .to(dtype=torch.float32).div(255.0).unsqueeze(0)
            ),
            "observation.state": torch.tensor(position, dtype=torch.float32).unsqueeze(0),
        }
        with torch.inference_mode():
            action = self.policy.select_action(batch)
        if tuple(action.shape) != (1, 2):
            raise ValueError("Diffusion policy must return one 2D PushT action")
        return _vector2(action.detach().cpu().numpy()[0], "policy action")

    def step(self, env: Any, action: list[float]) -> Any:
        return env.step(self.np.asarray(action, dtype=self.np.float32))


def _run_episode(
    runtime: Any, env: Any, *, seed: int, max_steps: int, action_scale: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.perf_counter()
    runtime.seed(seed)
    observation, _ = env.reset(seed=seed)
    trajectory: dict[str, Any] = {
        "schema_version": 1, "artifact_type": "lerobot_pusht_trajectory", "seed": seed,
        "initial_observation": _observation_record(observation), "steps": [],
    }
    rewards: list[float] = []
    inference_time = 0.0
    for step in range(1, max_steps + 1):
        position = _vector2(observation["agent_pos"], "agent position")
        inference_started = time.perf_counter()
        predicted = _vector2(runtime.predict(observation), "policy action")
        inference_time += time.perf_counter() - inference_started
        # Log precisely the float32 values passed to the simulator, not pre-cast doubles.
        action = [
            struct.unpack("<f", struct.pack(
                "<f", min(512.0, max(0.0, pos + action_scale * (target - pos))),
            ))[0]
            for pos, target in zip(position, predicted, strict=True)
        ]
        observation, raw_reward, terminated, truncated, info = runtime.step(env, action)
        reward = float(raw_reward)
        if not math.isfinite(reward) or not 0.0 <= reward <= 1.0:
            raise ValueError("PushT returned a non-finite or out-of-range reward")
        terminated, truncated = bool(terminated), bool(truncated)
        success = bool(info.get("is_success", terminated))
        if success != terminated:
            raise ValueError("PushT success and termination disagree")
        if step == max_steps and not terminated:
            truncated = True
        rewards.append(reward)
        trajectory["steps"].append({
            "step": step, "agent_pos": position, "policy_action": predicted, "action": action,
            "reward": reward, "terminated": terminated, "truncated": truncated,
            "success": success, "observation": _observation_record(observation),
        })
        if terminated or truncated:
            break
    episode = {
        "seed": seed, "steps": len(rewards), "success": success,
        "terminated": terminated, "truncated": truncated,
        "max_reward": max(rewards), "final_reward": rewards[-1],
        "sum_reward": math.fsum(rewards), "wall_time_s": time.perf_counter() - started,
        "inference_time_s": inference_time,
    }
    return episode, trajectory


def _validate_arguments(
    seeds: list[int], max_steps: int, num_inference_steps: int,
    action_scale: float, torch_threads: int,
) -> None:
    if (
        not isinstance(seeds, list) or not seeds or len(seeds) > 1000
        or any(type(seed) is not int or not 0 <= seed < 2**32 for seed in seeds)
        or len(set(seeds)) != len(seeds)
    ):
        raise ValueError("seeds must contain 1 to 1000 distinct integers in [0, 2**32)")
    for name, value, limit in (
        ("max_steps", max_steps, 10_000), ("torch_threads", torch_threads, 256),
    ):
        if type(value) is not int or not 1 <= value <= limit:
            raise ValueError(f"{name} must be an integer in [1, {limit}]")
    if type(num_inference_steps) is not int or not 1 <= num_inference_steps <= 100:
        raise ValueError("num_inference_steps must be an integer in [1, 100]")
    if isinstance(action_scale, bool) or not isinstance(action_scale, (int, float)):
        raise ValueError("action_scale must be a finite number in [0, 1]")
    if not math.isfinite(action_scale) or not 0 <= action_scale <= 1:
        raise ValueError("action_scale must be a finite number in [0, 1]")


def run_pusht(
    checkpoint: Path, output_dir: Path, *, seeds: list[int], max_steps: int = 300,
    num_inference_steps: int = 10, action_scale: float = 1.0, torch_threads: int = 1,
) -> dict[str, Any]:
    """Run paired-seed-ready evaluation and preserve its provenance and trajectories.

    The output directory must be new. Runtime/checkpoint failures are recorded as
    INFRA_ERROR; they never become unsuccessful robot episodes. Invalid arguments
    and an existing output directory raise before any evidence is written.
    """
    try:
        _validate_arguments(seeds, max_steps, num_inference_steps, action_scale, torch_threads)
        checkpoint, output_dir = Path(checkpoint).resolve(), Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=False)
    except (OSError, ValueError, TypeError) as exc:
        raise LeRobotRunnerError(str(exc)) from exc
    result: dict[str, Any] = {
        "schema_version": 1, "artifact_type": "lerobot_pusht_evaluation",
        "status": "INFRA_ERROR", "episodes": [],
    }
    try:
        from robotci.lerobot_checkpoint import verify_checkpoint

        manifest = verify_checkpoint(checkpoint)
        result["policy"] = {
            "checkpoint_id": manifest["source"]["repo_id"],
            "revision": manifest["source"]["revision"],
            "config_sha256": manifest["files"]["config.json"]["sha256"],
            "weights_sha256": manifest["files"]["model.safetensors"]["sha256"],
            "num_inference_steps": num_inference_steps, "action_scale": float(action_scale),
        }
        with _offline_environment(), contextlib.redirect_stdout(sys.stderr):
            runtime = _CpuRuntime()
            result["protocol"] = {
                "env_id": ENV_ID, "obs_type": OBS_TYPE, "max_steps": max_steps,
                "seeds": list(seeds), "device": "cpu", "torch_threads": torch_threads,
                "runtime": {
                    "python": platform.python_version(), "platform": platform.platform(),
                    "machine": platform.machine(),
                    "versions": runtime.versions,
                },
                "observation_shape": [3, 96, 96], "deterministic_algorithms": True,
                "inference_dtype": "float32", "control_hz": 10,
                "seed_strategy": "per_episode_python_numpy_torch_env_v1",
                "action_transform": "observed_position_plus_scaled_policy_delta_clipped_v1",
            }
            with runtime.settings(torch_threads):
                runtime.load_policy(checkpoint, num_inference_steps)
                env = runtime.make_env(max_steps)
                try:
                    for seed in seeds:
                        episode, trajectory = _run_episode(
                            runtime, env, seed=seed, max_steps=max_steps,
                            action_scale=float(action_scale),
                        )
                        episode["trajectory_sha256"] = _atomic_json(
                            output_dir / f"episode-{seed}.json", trajectory,
                        )
                        result["episodes"].append(episode)
                finally:
                    env.close()
        result["status"] = "COMPLETED"
        from robotci.lerobot_evaluation import validate_evaluation

        result = validate_evaluation(result)
    except Exception as exc:
        result["status"] = "INFRA_ERROR"
        result["error"] = {"type": type(exc).__name__, "message": str(exc)}
    try:
        _atomic_json(output_dir / "result.json", result)
    except (OSError, ValueError, TypeError) as exc:
        raise LeRobotRunnerError(f"Could not write evaluation result: {exc}") from exc
    return result
