"""Static URDF coupling must survive parsing without inventing joint motion."""
from __future__ import annotations

import hashlib
import json
from itertools import permutations
from pathlib import Path

import pytest

from robotci.model_import import ModelImportError, inspect_description
from robotci.model_mimic import resolve_mimic_reference


def _joint(
    name: str,
    *,
    kind: str = "prismatic",
    lower: str = "0",
    upper: str = "0.04",
    mimic: str = "",
    axis: str = "0 1 0",
) -> str:
    limit = (
        f'<limit lower="{lower}" upper="{upper}" effort="20" velocity="0.2"/>'
        if kind in {"prismatic", "revolute"} else ""
    )
    return (
        f'<link name="{name}_link"><visual><geometry><box size="0.02 0.01 0.06"/>'
        f'</geometry></visual></link><joint name="{name}" type="{kind}">'
        f'<parent link="base"/><child link="{name}_link"/><axis xyz="{axis}"/>'
        f'{limit}{mimic}</joint>'
    )


def _robot(*joints: str) -> str:
    return '<robot name="custom_hand"><link name="base"/>' + "".join(joints) + "</robot>"


def _values(text: str) -> dict:
    return {j["name"]: j for n in inspect_description(text)["nodes"] for j in n["joints"]}


@pytest.mark.parametrize("reverse", [False, True])
def test_default_coupling_retains_opposite_finger_axes_and_metadata(reverse: bool) -> None:
    joints = [
        _joint("leader", lower="0.01"),
        _joint("follower", mimic='<mimic joint="leader"/>', axis="0 -1 0"),
    ]
    text = _robot(*(reversed(joints) if reverse else joints))
    before = hashlib.sha256(text.encode()).hexdigest()
    result = inspect_description(text)
    values = _values(text)
    assert values["leader"]["value"] == values["follower"]["value"] == 0.01
    assert values["leader"]["axis"] == [0, 1, 0]
    assert values["follower"]["axis"] == [0, -1, 0]
    assert values["follower"]["mimic"] == {"joint": "leader", "multiplier": 1, "offset": 0}
    assert result["link_count"] == 3 and result["joint_count"] == 2
    assert result["visual_only"] and not result["simulation_ready"]
    assert result["identification"] == "structural" and result["model_id"] is None
    assert any("mimic" in warning for warning in result["warnings"])
    assert result["source_sha256"] == before == hashlib.sha256(text.encode()).hexdigest()
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("order", list(permutations(range(3))))
def test_chained_multipliers_offsets_are_resolved_independently_of_xml_order(order: tuple) -> None:
    parts = [
        _joint("a", lower="0.02"),
        _joint("b", upper="0.2", mimic='<mimic joint="a" multiplier="2" offset="0.005"/>'),
        _joint("c", upper="0.2", mimic='<mimic joint="b" multiplier="-1" offset="0.1"/>'),
    ]
    values = _values(_robot(*(parts[i] for i in order)))
    assert {name: j["value"] for name, j in values.items()} == pytest.approx(
        {"a": 0.02, "b": 0.045, "c": 0.055}
    )


@pytest.mark.parametrize(
    "multiplier,offset,lower,upper,leader,follower",
    [
        ("1", "0", "0.02", "0.04", 0.02, 0.02),
        ("-1", "0.04", "0.01", "0.02", 0.02, 0.02),
        ("0", "0.015", "0.01", "0.02", 0.0, 0.015),
        ("2", "0", "0.02", "0.03", 0.01, 0.02),
    ],
)
def test_reference_respects_both_leader_and_follower_limits(
    multiplier: str, offset: str, lower: str, upper: str, leader: float, follower: float,
) -> None:
    values = _values(_robot(
        _joint("leader"),
        _joint("follower", lower=lower, upper=upper,
               mimic=f'<mimic joint="leader" multiplier="{multiplier}" offset="{offset}"/>'),
    ))
    assert values["leader"]["value"] == pytest.approx(leader)
    assert values["follower"]["value"] == pytest.approx(follower)
    assert values["follower"]["value"] == pytest.approx(
        float(multiplier) * values["leader"]["value"] + float(offset)
    )
    for joint in values.values():
        assert joint["range"][0] <= joint["value"] <= joint["range"][1]


def test_decimal_boundary_does_not_invent_empty_feasible_interval() -> None:
    values = _values(_robot(
        _joint("leader", lower="0.1", upper="0.1"),
        _joint("follower", lower="0.3", upper="0.3",
               mimic='<mimic joint="leader" offset="0.2"/>'),
    ))
    assert values["leader"]["value"] == 0.1
    assert values["follower"]["value"] == 0.3


@pytest.mark.parametrize("kinds", [("continuous", "revolute"), ("revolute", "continuous")])
def test_angular_joint_types_share_radian_coordinate(kinds: tuple[str, str]) -> None:
    values = _values(_robot(
        _joint("leader", kind=kinds[0], lower="-2", upper="2"),
        _joint("follower", kind=kinds[1], lower="-2", upper="2",
               mimic='<mimic joint="leader" multiplier="-1" offset="0.5"/>'),
    ))
    assert values["leader"]["value"] == 0
    assert values["follower"]["value"] == 0.5


@pytest.mark.parametrize(
    "parts",
    [
        [_joint("a", mimic='<mimic joint="a"/>')],
        [_joint("a", mimic='<mimic joint="missing"/>')],
        [_joint("a", mimic='<mimic joint="b"/>'), _joint("b", mimic='<mimic joint="a"/>')],
        [_joint("a", mimic='<mimic joint="b" multiplier="0"/>'),
         _joint("b", mimic='<mimic joint="a"/>')],
        [_joint("a", kind="fixed"), _joint("b", mimic='<mimic joint="a"/>')],
        [_joint("a"), _joint("b", kind="fixed", mimic='<mimic joint="a"/>')],
        [_joint("a"), _joint("b", kind="revolute", mimic='<mimic joint="a"/>')],
        [_joint("a"), _joint("b", mimic='<mimic joint="a"/><mimic joint="a"/>')],
        [_joint("a"), _joint("b", mimic='<mimic/>')],
        [_joint("a"), _joint("b", mimic='<mimic joint=""/>')],
        [_joint("a"), _joint("b", mimic='<mimic joint="a" surprise="1"/>')],
        [_joint("a"), _joint("b", mimic='<mimic joint="a"><extra/></mimic>')],
    ],
)
def test_invalid_dependency_graph_is_rejected(parts: list[str]) -> None:
    with pytest.raises(ModelImportError):
        inspect_description(_robot(*parts))


@pytest.mark.parametrize("field", ["multiplier", "offset"])
@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "1e999", "10001", "bad", "", "0 1"])
def test_invalid_mimic_numbers_are_rejected(field: str, value: str) -> None:
    with pytest.raises(ModelImportError):
        inspect_description(_robot(
            _joint("leader"),
            _joint("follower", mimic=f'<mimic joint="leader" {field}="{value}"/>'),
        ))


@pytest.mark.parametrize("zero", [False, True])
def test_infeasible_reference_is_not_fixed_by_independent_clamping(zero: bool) -> None:
    with pytest.raises(ModelImportError, match="несовместимы"):
        inspect_description(_robot(
            _joint("a", lower="0.01"),
            _joint("b", upper="0.04",
                   mimic=f'<mimic joint="a" multiplier="{0 if zero else 1}" offset="0.1"/>'),
        ))


def test_conflicting_followers_are_rejected_together() -> None:
    with pytest.raises(ModelImportError, match="несовместимы"):
        inspect_description(_robot(
            _joint("a"),
            _joint("b", lower="0.01", upper="0.015", mimic='<mimic joint="a"/>'),
            _joint("c", lower="0.02", upper="0.03", mimic='<mimic joint="a"/>'),
        ))


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("depth", [48, 49])
def test_mimic_depth_budget_is_independent_of_link_depth_or_xml_order(
    reverse: bool, depth: int,
) -> None:
    parts = [_joint("j0")]
    parts.extend(_joint(f"j{i}", mimic=f'<mimic joint="j{i-1}"/>') for i in range(1, depth + 1))
    text = _robot(*(reversed(parts) if reverse else parts))
    if depth > 48:
        with pytest.raises(ModelImportError, match="глубокая"):
            inspect_description(text)
    else:
        assert all(j["value"] == 0 for j in _values(text).values())


def test_tiny_multiplier_chain_is_not_underflowed_to_constant() -> None:
    parts = [_joint("j0", lower="0.01")]
    parts.extend(
        _joint(f"j{i}", mimic=f'<mimic joint="j{i-1}" multiplier="1e-100"/>')
        for i in range(1, 5)
    )
    # A strictly positive follower cannot satisfy this tiny affine map within
    # the leader's limits. Rounding the composed factor to zero loses the map.
    parts[-1] = _joint("j4", lower="0.01", mimic='<mimic joint="j3" multiplier="1e-100"/>')
    with pytest.raises(ModelImportError, match="несовместимы"):
        inspect_description(_robot(*parts))


def test_failed_resolution_does_not_mutate_already_resolved_values() -> None:
    result = inspect_description(_robot(_joint("a"), _joint("b"), _joint("c")))
    nodes = result["nodes"]
    values = {j["name"]: j for node in nodes for j in node["joints"]}
    values["b"]["mimic"] = {"joint": "a", "multiplier": 1, "offset": 0.01}
    values["c"]["mimic"] = {"joint": "missing", "multiplier": 1, "offset": 0}
    before = json.dumps(nodes, sort_keys=True)
    with pytest.raises(ValueError):
        resolve_mimic_reference(nodes)
    assert json.dumps(nodes, sort_keys=True) == before


def test_plain_urdf_keeps_its_existing_reference_rule() -> None:
    text = _robot(_joint("a", lower="0.01"), _joint("b", lower="-2", upper="-1"))
    values = _values(text)
    assert values["a"]["value"] == 0.01
    assert values["b"]["value"] == -1
    assert all("mimic" not in j for j in values.values())
    assert not any("mimic" in w for w in inspect_description(text)["warnings"])


def test_shipped_gripper_example_has_one_compatible_reference() -> None:
    path = Path(__file__).parents[1] / "examples/robot-models/mimic-gripper.urdf"
    values = _values(path.read_text(encoding="utf-8"))
    assert values["left_finger_joint"]["value"] == 0.015
    assert values["right_finger_joint"]["value"] == 0.015
