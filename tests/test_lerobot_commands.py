from __future__ import annotations

import copy
import json
from importlib import metadata
from pathlib import Path

import pytest
from typer.testing import CliRunner

from robotci import lerobot_checkpoint, lerobot_cli, lerobot_runner
from robotci.cli import app
from robotci.lerobot_evaluation import RUNTIME_PACKAGES

runner = CliRunner()


def _evaluation() -> dict:
    return {
        "schema_version": 1, "artifact_type": "lerobot_pusht_evaluation", "status": "COMPLETED",
        "protocol": {
            "env_id": "gym_pusht/PushT-v0", "obs_type": "pixels_agent_pos", "device": "cpu",
            "observation_shape": [3, 96, 96], "deterministic_algorithms": True,
            "inference_dtype": "float32", "control_hz": 10,
            "seed_strategy": "per_episode_python_numpy_torch_env_v1",
            "action_transform": "observed_position_plus_scaled_policy_delta_clipped_v1",
            "max_steps": 2, "seeds": [1000], "torch_threads": 1,
            "runtime": {
                "python": "3.12.14", "platform": "synthetic-test", "machine": "x86_64",
                "versions": {name: "test-version" for name in RUNTIME_PACKAGES},
            },
        },
        "policy": {
            "checkpoint_id": "synthetic-cli-test", "revision": "a" * 40,
            "config_sha256": "b" * 64, "weights_sha256": "c" * 64,
            "num_inference_steps": 10, "action_scale": 1.0,
        },
        "episodes": [{
            "seed": 1000, "steps": 1, "success": True, "terminated": True, "truncated": False,
            "max_reward": 1.0, "final_reward": 1.0, "sum_reward": 1.0,
            "wall_time_s": 0.5, "inference_time_s": 0.25, "trajectory_sha256": "d" * 64,
        }],
    }


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.parametrize("status,code", [("PASS", 0), ("REGRESSION", 4), ("INFRA_ERROR", 3)])
def test_compare_real_reader_gate_reports_and_exit_codes(
    tmp_path: Path, status: str, code: int
) -> None:
    baseline = _evaluation()
    candidate = copy.deepcopy(baseline)
    if status == "REGRESSION":
        candidate["policy"]["action_scale"] = 0.0
        candidate["episodes"][0].update(
            steps=2, success=False, terminated=False, truncated=True,
            max_reward=0.2, final_reward=0.1, sum_reward=0.3,
        )
    elif status == "INFRA_ERROR":
        candidate["protocol"]["torch_threads"] = 2
    base_path, candidate_path = tmp_path / "base.json", tmp_path / "candidate.json"
    _write(base_path, baseline)
    _write(candidate_path, candidate)
    before = base_path.read_bytes(), candidate_path.read_bytes()
    result = runner.invoke(app, [
        "lerobot", "compare", str(base_path), str(candidate_path), "--json",
        "--output", str(tmp_path / "reports" / "result.json"),
        "--markdown", str(tmp_path / "reports" / "result.md"),
    ])
    assert result.exit_code == code, result.output
    report = json.loads(result.stdout)
    assert report["status"] == status
    assert json.loads((tmp_path / "reports" / "result.json").read_text()) == report
    assert status in (tmp_path / "reports" / "result.md").read_text()
    assert (base_path.read_bytes(), candidate_path.read_bytes()) == before


def test_missing_compare_input_is_a_json_infrastructure_error(tmp_path: Path) -> None:
    result = runner.invoke(app, [
        "lerobot", "compare", str(tmp_path / "missing"), str(tmp_path / "candidate"), "--json"
    ])
    assert result.exit_code == 3
    assert json.loads(result.stdout)["status"] == "INFRA_ERROR"


def test_existing_output_refuses_to_overwrite_either_report(tmp_path: Path) -> None:
    source = tmp_path / "result.json"
    _write(source, _evaluation())
    before = source.read_bytes()
    markdown = tmp_path / "report.md"
    result = runner.invoke(app, [
        "lerobot", "compare", str(source), str(source), "--json",
        "--output", str(source), "--markdown", str(markdown),
    ])
    assert result.exit_code == 3
    assert json.loads(result.stdout)["status"] == "INFRA_ERROR"
    assert source.read_bytes() == before
    assert not markdown.exists()


def test_report_preparation_error_leaves_no_successful_json(tmp_path: Path) -> None:
    source = tmp_path / "result.json"
    _write(source, _evaluation())
    impossible = tmp_path / "not-a-directory"
    impossible.write_bytes(b"preserve")
    output = tmp_path / "report.json"
    result = runner.invoke(app, [
        "lerobot", "compare", str(source), str(source), "--json", "--output", str(output),
        "--markdown", str(impossible / "report.md"),
    ])
    assert result.exit_code == 3
    assert json.loads(result.stdout)["status"] == "INFRA_ERROR"
    assert not output.exists()
    assert impossible.read_bytes() == b"preserve"


def test_second_report_publish_failure_rolls_back_only_new_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_link = lerobot_cli.os.link

    def fail_json(source, destination, *args, **kwargs):
        if Path(destination).suffix == ".json":
            raise OSError("simulated storage failure")
        return original_link(source, destination, *args, **kwargs)

    monkeypatch.setattr(lerobot_cli.os, "link", fail_json)
    with pytest.raises(OSError, match="simulated storage failure"):
        lerobot_cli._save_reports(
            {"status": "PASS"}, tmp_path / "report.json", tmp_path / "report.md"
        )
    assert list(tmp_path.iterdir()) == []


def test_report_alias_paths_are_rejected_before_writes(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="different output"):
        lerobot_cli._save_reports(
            {"status": "PASS"}, tmp_path / "report", tmp_path / "sub" / ".." / "report"
        )
    assert list(tmp_path.iterdir()) == []


def test_run_cli_passes_explicit_experiment_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def fake_run(checkpoint, output_dir, **kwargs):
        calls.append((checkpoint, output_dir, kwargs))
        return _evaluation()

    monkeypatch.setattr(lerobot_runner, "run_pusht", fake_run)
    result = runner.invoke(app, [
        "lerobot", "run", str(tmp_path / "checkpoint"), "--output", str(tmp_path / "run"),
        "--seed", "11", "--seed", "12", "--action-scale", "0", "--inference-steps", "20",
        "--max-steps", "150", "--threads", "2", "--json",
    ])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "COMPLETED"
    assert calls == [(tmp_path / "checkpoint", tmp_path / "run", {
        "seeds": [11, 12], "max_steps": 150, "num_inference_steps": 20,
        "action_scale": 0.0, "torch_threads": 2,
    })]


def test_missing_optional_runtime_is_preserved_as_infrastructure_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        lerobot_checkpoint, "verify_checkpoint", lambda _: copy.deepcopy(
            lerobot_checkpoint.PINNED_CHECKPOINT
        )
    )

    def unavailable():
        raise metadata.PackageNotFoundError("torch")

    monkeypatch.setattr(lerobot_runner, "_CpuRuntime", unavailable)
    output = tmp_path / "run"
    result = runner.invoke(app, [
        "lerobot", "run", str(tmp_path / "checkpoint"), "--output", str(output), "--json"
    ])
    assert result.exit_code == 3, result.output
    report = json.loads(result.stdout)
    assert report["status"] == "INFRA_ERROR"
    assert report["episodes"] == []
    assert report["error"]["type"] == "PackageNotFoundError"
    assert json.loads((output / "result.json").read_text()) == report


def test_run_refuses_existing_output_and_duplicate_seeds(tmp_path: Path) -> None:
    marker = tmp_path / "keep.txt"
    marker.write_text("original", encoding="utf-8")
    for flags in ([], ["--seed", "1", "--seed", "1"]):
        result = runner.invoke(app, [
            "lerobot", "run", "missing-checkpoint", "--output", str(tmp_path), "--json", *flags
        ])
        assert result.exit_code == 3, result.output
        assert json.loads(result.stdout)["status"] == "INFRA_ERROR"
        assert marker.read_text() == "original"
        assert not (tmp_path / "result.json").exists()


def test_run_result_write_failure_still_emits_json_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unwritable(*args):
        raise OSError("No space left on device")

    monkeypatch.setattr(lerobot_runner, "_atomic_json", unwritable)
    result = runner.invoke(app, [
        "lerobot", "run", "missing-checkpoint", "--output", str(tmp_path / "run"), "--json"
    ])
    assert result.exit_code == 3, result.output
    assert json.loads(result.stdout)["status"] == "INFRA_ERROR"


def test_fetch_error_is_json_without_optional_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args):
        raise lerobot_checkpoint.LeRobotCheckpointError("Hash mismatch")

    monkeypatch.setattr(lerobot_checkpoint, "fetch_checkpoint", fail)
    result = runner.invoke(app, ["lerobot", "fetch", str(tmp_path / "checkpoint"), "--json"])
    assert result.exit_code == 3
    assert json.loads(result.stdout)["status"] == "INFRA_ERROR"
