from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from robotci.cli import app

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "lerobot-preflight"
runner = CliRunner()


def test_example_and_main_cli_registration() -> None:
    result = runner.invoke(
        app,
        [
            "lerobot", "inspect", str(EXAMPLE / "dataset"),
            "--policy", str(EXAMPLE / "policy"),
            "--robot-type", "so101_follower", "--fps", "30", "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report["status"] == "VALID"
    assert report["scope"] == "metadata_only"
    camera = report["dataset"]["features"]["observation.images.front"]
    assert camera["policy_shape"] == [3, 480, 640]
    assert report["policy"]["type"] == "act"
    assert len(report["files"]["dataset_info"]["sha256"]) == 64


@pytest.mark.parametrize("flags", [["--fps", "10"], ["--robot-type", "unitree_g1"]])
def test_mismatched_expectations_block_preflight(flags: list[str]) -> None:
    result = runner.invoke(app, ["lerobot", "inspect", str(EXAMPLE / "dataset"), *flags, "--json"])
    assert result.exit_code == 3
    assert json.loads(result.stdout)["status"] == "INVALID"


def test_candidate_action_change_is_rejected_without_modifying_inputs(tmp_path: Path) -> None:
    original = (EXAMPLE / "policy" / "config.json").read_bytes()
    candidate = json.loads(original)
    candidate["output_features"]["action"]["shape"] = [7]
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(candidate), encoding="utf-8")
    before = path.read_bytes()
    result = runner.invoke(
        app, ["lerobot", "inspect", str(EXAMPLE / "dataset"), "--policy", str(path), "--json"]
    )
    assert result.exit_code == 3
    report = json.loads(result.stdout)
    assert report["status"] == "INVALID"
    assert "policy_shape_mismatch" in {issue["code"] for issue in report["issues"]}
    assert path.read_bytes() == before
    assert (EXAMPLE / "policy" / "config.json").read_bytes() == original


def test_unsupported_policy_never_returns_success(tmp_path: Path) -> None:
    policy = json.loads((EXAMPLE / "policy" / "config.json").read_text(encoding="utf-8"))
    policy["type"] = "unknown_policy"
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    result = runner.invoke(
        app, ["lerobot", "inspect", str(EXAMPLE / "dataset"), "--policy", str(path), "--json"]
    )
    assert result.exit_code == 3
    assert json.loads(result.stdout)["status"] == "UNSUPPORTED"


def test_missing_metadata_returns_json_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["lerobot", "inspect", str(tmp_path / "missing.json"), "--json"])
    assert result.exit_code == 3
    report = json.loads(result.stdout)
    assert report["scope"] == "metadata_only"
    assert report["issues"][0]["code"] == "input_error"


def test_human_output_states_scope() -> None:
    result = runner.invoke(app, ["lerobot", "inspect", str(EXAMPLE / "dataset")])
    assert result.exit_code == 0
    assert "только метаданные" in result.stdout
    assert "не проверены" in result.stdout


@pytest.mark.parametrize("command", ["lerobot", "model"])
def test_isolated_bootstrap_exposes_new_commands(tmp_path: Path, command: str) -> None:
    args = (
        ["inspect", str(EXAMPLE / "dataset"), "--json"]
        if command == "lerobot" else ["list", "--json"]
    )
    result = subprocess.run(
        [sys.executable, "-m", "robotci.bootstrap", command, *args],
        cwd=tmp_path, capture_output=True, text=True, timeout=20, check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["schema_version"] == 1
