from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from robotci.model_cli import model_app
from robotci.model_import import MAX_DESCRIPTION_BYTES, inspect_description

runner = CliRunner()
CATALOG_CASES = [
    ("unitree_go2", "quadruped", 13, 12),
    ("unitree_g1", "humanoid", 30, 29),
    ("franka_emika_panda", "manipulator", 11, 9),
]
MINIMAL_URDF = '<robot name="мой робот"><link name="base"/></robot>'


def test_list_reports_all_offline_pinned_models_without_terminal_formatting() -> None:
    result = runner.invoke(model_app, ["list", "--json"], color=True, env={"COLUMNS": "30"})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert result.stderr == ""
    assert payload["schema_version"] == 1
    assert payload["kind"] == "robot_model_catalog"
    assert payload["scope"] == "static_reference"
    assert payload["offline"] is True
    assert payload["mesh_files_checked"] is False
    assert len(payload["models"]) == 3
    models = {model["model_id"]: model for model in payload["models"]}
    assert set(models) == {case[0] for case in CATALOG_CASES}
    for model_id, kind, links, joints in CATALOG_CASES:
        model = models[model_id]
        assert model["classification"]["kind"] == kind
        assert (model["link_count"], model["joint_count"]) == (links, joints)
        assert model["provenance"]["repository"] == "google-deepmind/mujoco_menagerie"
        assert model["provenance"]["revision"] == "0059d4335f8156206f63a35662313385f7ad6d74"
        assert model["provenance"]["file"].startswith(f"{model_id}/")
        assert model["geometry"]["triangles"] > 100_000
    assert "\x1b" not in result.stdout


@pytest.mark.parametrize("model_id,kind,links,joints", CATALOG_CASES)
def test_inspect_catalog_selection_keeps_complete_description(
    tmp_path: Path, model_id: str, kind: str, links: int, joints: int
) -> None:
    text = f"robot:\n  model: {model_id}\n"
    path = tmp_path / "selection.yaml"
    path.write_text(text, encoding="utf-8")
    result = runner.invoke(model_app, ["inspect", str(path), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert result.stderr == ""
    assert payload["kind"] == "robot_model_inspection"
    assert payload["schema_version"] == 1
    assert payload["scope"] == "static_reference"
    assert payload["mesh_files_checked"] is False
    description = payload["description"]
    assert description == inspect_description(text)
    assert description["classification"]["kind"] == kind
    assert description["identification"] == "declared_catalog"
    assert description["model_id"] == model_id
    assert description["simulation_ready"] is False
    assert (description["link_count"], description["joint_count"]) == (links, joints)
    assert len(description["nodes"]) == links
    assert sum(len(node["joints"]) for node in description["nodes"]) == joints
    assert any(node["visuals"] for node in description["nodes"])
    assert "verdict" not in payload
    assert "status" not in payload


def test_file_hash_uses_exact_bytes_including_bom_and_crlf(tmp_path: Path) -> None:
    raw = b"\xef\xbb\xbf" + (MINIMAL_URDF + "\r\n").encode("utf-8")
    path = tmp_path / "robot.urdf"
    path.write_bytes(raw)
    result = runner.invoke(model_app, ["inspect", str(path), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["source_file"] == {
        "path": str(path),
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    assert payload["source_file"]["sha256"] != payload["description"]["source_sha256"]
    assert payload["description"]["name"] == "мой робот"


def test_brand_name_does_not_claim_catalog_identity(tmp_path: Path) -> None:
    path = tmp_path / "go2.urdf"
    path.write_text('<robot name="Unitree Go2"><link name="base"/></robot>', encoding="utf-8")
    result = runner.invoke(model_app, ["inspect", str(path), "--json"])
    assert result.exit_code == 0, result.output
    description = json.loads(result.stdout)["description"]
    assert description["model_id"] is None
    assert description["classification"]["kind"] == "unknown"
    assert description["classification"]["confidence"] == "low"
    assert description["identification"] == "structural"


def test_mimic_gripper_inspection_preserves_constraint_and_reference_pose() -> None:
    path = Path(__file__).parents[1] / "examples/robot-models/mimic-gripper.urdf"
    result = runner.invoke(model_app, ["inspect", str(path), "--json"])
    assert result.exit_code == 0, result.output
    description = json.loads(result.stdout)["description"]
    joints = {joint["name"]: joint for node in description["nodes"] for joint in node["joints"]}
    assert len(joints) == 2
    follower = joints["right_finger_joint"]
    assert follower["mimic"] == {
        "joint": "left_finger_joint",
        "multiplier": 1.0,
        "offset": 0.0,
    }
    assert follower["value"] == pytest.approx(0.015)
    assert joints["left_finger_joint"]["value"] == pytest.approx(0.015)
    assert any("mimic" in warning for warning in description["warnings"])
    assert description["simulation_ready"] is False


@pytest.mark.parametrize(
    "raw,code",
    [
        (b"<robot>", "invalid_description"),
        (b"runtime: docker\n", "invalid_description"),
        (b"robot: {model: unknown}\n", "invalid_description"),
        (b"\xff\xfe<\x00r\x00o\x00b\x00o\x00t\x00", "invalid_encoding"),
        (b"\x80\x81\xff", "invalid_encoding"),
        (b"x" * (MAX_DESCRIPTION_BYTES + 1), "description_too_large"),
    ],
    ids=[
        "malformed_xml",
        "scenario_only_yaml",
        "unknown_catalog_model",
        "utf16_xml",
        "invalid_utf8",
        "description_too_large",
    ],
)
def test_invalid_file_is_json_with_input_error_exit(tmp_path: Path, raw: bytes, code: str) -> None:
    path = tmp_path / "invalid.xml"
    path.write_bytes(raw)
    result = runner.invoke(model_app, ["inspect", str(path), "--json"])
    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == code
    assert payload["error"]["message"]
    assert payload["kind"] == "robot_model_inspection"
    assert payload["schema_version"] == 1
    assert "description" not in payload
    assert result.stderr == ""
    assert path.read_bytes() == raw


@pytest.mark.parametrize("existing_directory", [False, True])
def test_missing_and_directory_inputs_are_typed_json_errors(
    tmp_path: Path, existing_directory: bool
) -> None:
    path = tmp_path if existing_directory else tmp_path / "missing.urdf"
    result = runner.invoke(model_app, ["inspect", str(path), "--json"])
    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == ("not_regular_file" if existing_directory else "io_error")
    assert result.stderr == ""


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO is unavailable on Windows")
def test_fifo_is_rejected_before_attempting_to_read(tmp_path: Path) -> None:
    path = tmp_path / "pipe.urdf"
    os.mkfifo(path)
    result = runner.invoke(model_app, ["inspect", str(path), "--json"])
    assert result.exit_code == 3
    assert json.loads(result.stdout)["error"]["code"] == "not_regular_file"


@pytest.mark.parametrize(
    "args",
    [
        ["inspect", "--json"],
        ["inspect", "robot.urdf", "--bad", "--json"],
        ["list", "--bad", "--json"],
    ],
)
def test_argument_errors_use_standard_typer_exit(args: list[str]) -> None:
    result = runner.invoke(model_app, args)
    assert result.exit_code == 2
    assert "Usage:" in result.output


def test_inspection_never_opens_referenced_meshes_or_changes_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mesh = tmp_path / "private.obj"
    mesh.write_bytes(b"PRIVATE_DO_NOT_READ")
    path = tmp_path / "robot.urdf"
    path.write_text(
        '<robot name="custom"><link name="base"><visual><geometry>'
        '<mesh filename="private.obj"/></geometry></visual></link></robot>',
        encoding="utf-8",
    )
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.iterdir()}
    original_path_open = Path.open
    original_os_open = os.open

    def guarded_path_open(target: Path, *args, **kwargs):
        assert target.name != mesh.name, "The referenced mesh must not be read"
        return original_path_open(target, *args, **kwargs)

    def guarded_os_open(target, flags, *args, **kwargs):
        assert Path(target).name != mesh.name, "The referenced mesh must not be read"
        assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
        return original_os_open(target, flags, *args, **kwargs)

    with monkeypatch.context() as guard:
        guard.setattr(Path, "open", guarded_path_open)
        guard.setattr(os, "open", guarded_os_open)
        result = runner.invoke(model_app, ["inspect", str(path), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["mesh_files_checked"] is False
    assert payload["description"]["nodes"][0]["visuals"][0]["file"] == "private.obj"
    assert "PRIVATE_DO_NOT_READ" not in result.stdout
    after = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.iterdir()}
    assert after == before


def test_human_output_names_limits_and_warnings(tmp_path: Path) -> None:
    path = tmp_path / "robot.urdf"
    path.write_text(MINIMAL_URDF, encoding="utf-8")
    result = runner.invoke(model_app, ["inspect", str(path)])
    assert result.exit_code == 0, result.output
    assert "Модель: мой робот; формат: URDF" in result.stdout
    assert "Тип: не определён; уверенность: низкая" in result.stdout
    assert "model_id: не установлен" in result.stdout
    assert "Звеньев: 1; суставов: 0" in result.stdout
    assert "mesh_files_checked=false" in result.stdout
    assert "Предупреждение:" in result.stdout
    assert "сценарии не проверялись" in result.stdout
    assert "PASS" not in result.stdout
    assert "FAIL" not in result.stdout
