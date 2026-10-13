"""Inspection is a read-only presentation operation, not robot control."""

from __future__ import annotations

import gzip
import hashlib
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from robotci.config import ConfigError, load_config
from robotci.model_import import CATALOG, CATALOG_DIR, ModelImportError, inspect_description
from robotci.viewer import create_viewer_server, demo_replay

URDF = """<robot name="my_robot">
<link name="base"><visual><geometry><box size="0.4 0.2 0.1"/></geometry></visual></link>
<link name="left_wheel"><visual><geometry>
<cylinder radius="0.06" length="0.03"/></geometry></visual></link>
<link name="right_wheel"/>
<joint name="left_wheel_joint" type="continuous"><parent link="base"/><child link="left_wheel"/>
<origin xyz="0 0.13 0" rpy="1.5707963267948966 0 0"/><axis xyz="0 0 1"/></joint>
<joint name="right_wheel_joint" type="continuous"><parent link="base"/><child link="right_wheel"/>
<origin xyz="0 -0.13 0"/><axis xyz="0 1 0"/></joint></robot>"""


def test_urdf_geometry_and_conservative_identity() -> None:
    result = inspect_description(URDF)
    assert result["classification"]["kind"] == "wheeled"
    assert result["model_id"] is None
    assert result["link_count"] == 3 and result["joint_count"] == 2
    assert result["nodes"][0]["visuals"][0]["size"] == [0.4, 0.2, 0.1]
    assert result["nodes"][1]["pos"] == [0, 0.13, 0]
    assert result["nodes"][1]["quat"][0] == pytest.approx(2**-0.5)
    assert result["simulation_ready"] is False
    assert result["visual_only"] is True


def test_manufacturer_name_is_not_proof_of_model_or_robot_type() -> None:
    result = inspect_description('<robot name="Unitree G1"><link name="base"/></robot>')
    assert result["model_id"] is None
    assert result["classification"]["kind"] == "unknown"
    assert result["classification"]["confidence"] == "low"


@pytest.mark.parametrize(
    "model_id,joints,kind",
    [
        ("unitree_go2", 12, "quadruped"),
        ("unitree_g1", 29, "humanoid"),
        ("franka_emika_panda", 9, "manipulator"),
    ],
)
def test_explicit_catalog_selection(model_id: str, joints: int, kind: str) -> None:
    result = inspect_description(f"robot:\n  model: {model_id}\n")
    assert result["model_id"] == model_id
    assert result["joint_count"] == joints
    assert result["classification"]["kind"] == kind
    assert result["identification"] == "declared_catalog"
    assert result["simulation_ready"] is False
    assert result["provenance"]["revision"] == "0059d4335f8156206f63a35662313385f7ad6d74"
    # A compressed GLB is a self-contained model, not an external URL.
    glb = gzip.decompress((CATALOG_DIR / result["catalog_asset"]).read_bytes())
    assert glb[:4] == b"glTF"
    assert b"https://" not in glb
    assert (CATALOG_DIR / f"{model_id}.LICENSE").stat().st_size > 1000


@pytest.mark.parametrize(
    "text",
    [
        "",
        "[]",
        "robot: {model: unknown}",
        "runtime: native",
        "robot: {model: 12}",
        "robot: {model: unitree_g1, model: unitree_go2}",
        "robot: &r {model: unitree_g1}",
        "robot: !!python/object:os.system {}",
        "<robot>",
        "<other/>",
        '<!DOCTYPE robot [<!ENTITY x "y">]><robot name="x"><link name="&x;"/></robot>',
        '<robot name="x"><xacro:include filename="x" xmlns:xacro="http://xacro"/></robot>',
        '<robot name="${execute}"><link name="base"/></robot>',
        '<robot name="r"><link name="base"/><link name="base"/></robot>',
        '<robot name="r"><link name="a"/><link name="b"/></robot>',
        '<robot name="r">'
        '<link name="a"/>'
        '<link name="b"/>'
        '<joint name="j" type="fixed">'
        '<parent link="b"/>'
        '<child link="a"/>'
        "</joint>"
        '<joint name="k" type="fixed">'
        '<parent link="a"/>'
        '<child link="b"/>'
        "</joint>"
        "</robot>",
        '<robot name="r">'
        '<link name="b">'
        "<visual>"
        "<geometry>"
        '<box size="NaN 1 2"/>'
        "</geometry>"
        "</visual>"
        "</link>"
        "</robot>",
        '<robot name="r">'
        '<link name="b">'
        "<visual>"
        "<geometry>"
        '<box size="-1 1 2"/>'
        "</geometry>"
        "</visual>"
        "</link>"
        "</robot>",
        '<robot name="r"><link name="b"><visual><geometry>'
        "<box/></geometry></visual></link></robot>",
        '<mujoco><include file="g1.xml"/></mujoco>',
        '<mujoco><worldbody><body name="r"><plugin plugin="external"/></body></worldbody></mujoco>',
        '<mujoco><worldbody><body name="r"><joint type="ball"/></body></worldbody></mujoco>',
        '<robot name="r">'
        '<link name="b">'
        "<visual>"
        "<geometry>"
        '<mesh filename="https://example.org/r.obj"/>'
        "</geometry>"
        "</visual>"
        "</link>"
        "</robot>",
        '<robot name="r">'
        '<link name="b">'
        "<visual>"
        "<geometry>"
        '<mesh filename="file:///private/r.obj"/>'
        "</geometry>"
        "</visual>"
        "</link>"
        "</robot>",
    ],
)
def test_malformed_unsafe_and_insufficient_descriptions_fail(text: str) -> None:
    with pytest.raises(ModelImportError):
        inspect_description(text)


def test_local_mesh_is_only_a_reference_not_a_file_read(tmp_path: Path) -> None:
    private = tmp_path / "private.obj"
    private.write_text("PRIVATE_DO_NOT_READ")
    text = (
        '<robot name="r">'
        '<link name="b">'
        "<visual>"
        "<geometry>"
        '<mesh filename="private.obj" scale="1 2 3"/>'
        "</geometry>"
        "</visual>"
        "</link>"
        "</robot>"
    )
    result = inspect_description(text)
    assert result["nodes"][0]["visuals"][0]["file"] == "private.obj"
    assert "PRIVATE_DO_NOT_READ" not in json.dumps(result)


def test_limits_units_defaults_and_keyframe() -> None:
    text = """<mujoco model="test">
<default><default class="limb"><joint axis="0 1 0" range="-90 90"/>
<geom type="box" size=".1 .2 .3"/></default></default>
<worldbody><body name="base" childclass="limb"><body name="arm" pos="0 0 1">
<joint name="hinge"/><geom/></body></body></worldbody>
<keyframe><key name="home" qpos="0.4"/></keyframe></mujoco>"""
    result = inspect_description(text)
    arm = result["nodes"][1]
    assert arm["joints"][0]["range"] == pytest.approx([-1.5707963267948966, 1.5707963267948966])
    assert arm["joints"][0]["value"] == 0.4
    assert arm["joints"][0]["axis"] == [0, 1, 0]
    assert arm["visuals"][0]["size"] == [0.2, 0.4, 0.6]


def test_size_and_depth_budgets() -> None:
    with pytest.raises(ModelImportError):
        inspect_description(" " * (2 * 1024 * 1024) + "x")
    with pytest.raises(ModelImportError):
        inspect_description(
            "<mujoco><worldbody>" + "<body>" * 50 + "</body>" * 50 + "</worldbody></mujoco>"
        )


def test_config_model_is_presentation_metadata_not_runtime(tmp_path: Path) -> None:
    config = tmp_path / "robotci.yaml"
    base = (
        "version: 1\nruntime: docker\nscenarios:\n  - name: demo\n"
        "    start: {x: 0, y: 0}\n    goal: {x: 1, y: 1}\n"
    )
    config.write_text(base + "robot: {model: unitree_go2}\n")
    result = load_config(config)
    assert result.robot.model == "unitree_go2"
    assert result.robot.visual_profile == "quadruped"
    assert result.runtime == "docker"
    config.write_text(base + "robot: {model: spoofed}\n")
    with pytest.raises(ConfigError):
        load_config(config)


@pytest.fixture
def http_model_server():
    server = create_viewer_server(demo_replay(), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_http_import_preserves_replay_and_serves_real_asset(http_model_server: str) -> None:
    base = http_model_server
    with urllib.request.urlopen(base + "/api/replay") as response:
        original = response.read()
    with urllib.request.urlopen(base + "/api/robot-model/catalog") as response:
        catalog = json.load(response)
    assert set(catalog["models"]) == set(CATALOG)
    request = urllib.request.Request(
        base + "/api/robot-model/inspect",
        method="POST",
        data=json.dumps({"text": URDF}).encode(),
        headers={"Content-Type": "application/json", "X-RobotCI-Model-Token": catalog["token"]},
    )
    with urllib.request.urlopen(request) as response:
        assert json.load(response)["joint_count"] == 2
    with urllib.request.urlopen(base + "/api/replay") as response:
        assert hashlib.sha256(response.read()).digest() == hashlib.sha256(original).digest()
    with urllib.request.urlopen(base + "/api/robot-model/asset/unitree_go2") as response:
        assert response.headers["Content-Encoding"] == "gzip"
        assert gzip.decompress(response.read())[:4] == b"glTF"


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-RobotCI-Model-Token": "wrong"},
        {"Host": "evil.example"},
        {"Origin": "https://evil.example"},
    ],
)
def test_http_import_requires_local_origin_and_session(
    http_model_server: str, headers: dict
) -> None:
    with urllib.request.urlopen(http_model_server + "/api/robot-model/catalog") as response:
        token = json.load(response)["token"]
    values = {"Content-Type": "application/json", **headers}
    if "Host" in headers or "Origin" in headers:
        values["X-RobotCI-Model-Token"] = token
    request = urllib.request.Request(
        http_model_server + "/api/robot-model/inspect",
        method="POST",
        headers=values,
        data=json.dumps({"text": URDF}).encode(),
    )
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request)
    assert error.value.code == 403
