import json
from pathlib import Path

import pytest

from robotci.config import ConfigError, PoseConfig, get_scenario, load_config


def test_load_config_reads_valid_robotci_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "robotci.yaml"

    config_path.write_text(
        """
version: 1
runtime: docker

scenarios:
  - name: test_route
    map_id: warehouse-map@sha256:abc123
    start:
      x: 0.0
      y: 0.0
      yaw: 0.0
    goal:
      x: 4.0
      y: -0.17
      yaw: 0.5
    timeout_sec: 45
    goal_tolerance_m: 0.4
    min_feedback_samples: 3
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.version == 1
    assert config.runtime == "docker"
    assert len(config.scenarios) == 1

    scenario = config.scenarios[0]
    assert scenario.name == "test_route"
    assert scenario.start.x == 0.0
    assert scenario.start.y == 0.0
    assert scenario.start.yaw == 0.0
    assert scenario.goal.x == 4.0
    assert scenario.goal.y == -0.17
    assert scenario.goal.yaw == 0.5
    assert scenario.timeout_sec == 45.0
    assert scenario.map_id == "warehouse-map@sha256:abc123"
    assert scenario.goal_tolerance_m == 0.4
    assert scenario.min_feedback_samples == 3


def test_load_config_accepts_utf8_bom(tmp_path: Path) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text(
        "version: 1\nscenarios:\n  - name: route\n    start: {x: 0, y: 0}\n"
        "    goal: {x: 1, y: 1}\n",
        encoding="utf-8-sig",
    )

    assert load_config(config_path).scenarios[0].name == "route"


def test_load_config_rejects_invalid_utf8_with_config_error(tmp_path: Path) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_bytes(b"version: 1\n# invalid UTF-8: \xff\n")

    with pytest.raises(ConfigError, match="Failed to read") as error:
        load_config(config_path)

    assert isinstance(error.value.__cause__, UnicodeDecodeError)


def test_load_config_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="config not found"):
        load_config(tmp_path / "robotci.yaml")


def test_load_config_rejects_unknown_version(tmp_path: Path) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text(
        "version: 999\nruntime: auto\nscenarios: []\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="version must be 1"):
        load_config(config_path)


def test_load_config_rejects_invalid_runtime(tmp_path: Path) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text(
        """
version: 1
runtime: windows
scenarios:
  - name: route
    start: {x: 0, y: 0}
    goal: {x: 1, y: 1}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="runtime must be one of"):
        load_config(config_path)


def test_load_config_rejects_duplicate_scenario_names(tmp_path: Path) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text(
        """
version: 1
scenarios:
  - name: route
    start: {x: 0, y: 0}
    goal: {x: 1, y: 1}
  - name: route
    start: {x: 0, y: 0}
    goal: {x: 2, y: 2}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="scenario names must be unique"):
        load_config(config_path)


@pytest.mark.parametrize(
    ("first", "second"),
    [("Foo", "foo"), ("route", "Route"), ("NAV-1", "nav-1"), (" foo ", "Foo")],
)
def test_load_config_rejects_case_insensitive_scenario_collisions(
    tmp_path: Path, first: str, second: str,
) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text(
        json.dumps({
            "version": 1,
            "scenarios": [
                {"name": name, "start": {"x": 0, "y": 0}, "goal": {"x": 1, "y": 1}}
                for name in (first, second)
            ],
        }),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="scenario names must be unique") as error:
        load_config(config_path)

    assert str(error.value) == (
        "scenario names must be unique (case-insensitive): "
        f"scenarios[1].name '{second.strip()}' conflicts with "
        f"scenarios[0].name '{first.strip()}'"
    )


@pytest.mark.parametrize(
    "name",
    [
        spelling
        for device in (
            "CON", "PRN", "AUX", "NUL",
            *(f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)),
        )
        for spelling in (device, device.lower())
    ] + ["CoN", "cOm1", "LpT9", " NUL "],
)
def test_load_config_rejects_windows_device_scenario_names(
    tmp_path: Path, name: str,
) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text(
        json.dumps({
            "version": 1,
            "scenarios": [
                {"name": name, "start": {"x": 0, "y": 0}, "goal": {"x": 1, "y": 1}},
            ],
        }),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="reserved on Windows") as error:
        load_config(config_path)

    assert str(error.value) == (
        f"scenarios[0].name '{name.strip()}' is reserved on Windows; "
        "choose a portable scenario name"
    )


def test_load_config_preserves_portable_names_similar_to_windows_devices(tmp_path: Path) -> None:
    names = ["Console", "Null", "AUX-route", "NUL_1", "COM0", "com10", "LPT0", "lpt10"]
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text(
        json.dumps({
            "version": 1,
            "scenarios": [
                {"name": name, "start": {"x": 0, "y": 0}, "goal": {"x": 1, "y": 1}}
                for name in names
            ],
        }),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert [scenario.name for scenario in config.scenarios] == names
    assert get_scenario(config, "COM0").name == "COM0"
    with pytest.raises(ConfigError, match="unknown scenario 'com0'"):
        get_scenario(config, "com0")


@pytest.mark.parametrize("name", ["../escape", "CON.txt", "nul.json", "COM1.replay"])
def test_load_config_rejects_unsafe_scenario_name(tmp_path: Path, name: str) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text(
        f"""
version: 1
scenarios:
  - name: {name}
    start: {{x: 0, y: 0}}
    goal: {{x: 1, y: 1}}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="only letters, numbers"):
        load_config(config_path)


def test_load_config_rejects_non_positive_timeout(tmp_path: Path) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text(
        """
version: 1
scenarios:
  - name: route
    start: {x: 0, y: 0}
    goal: {x: 1, y: 1}
    timeout_sec: 0
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="timeout_sec must be greater than zero"):
        load_config(config_path)


@pytest.mark.parametrize("value", ["0", "-1", ".nan", ".inf"])
def test_load_config_rejects_invalid_goal_tolerance(
    tmp_path: Path,
    value: str,
) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text(
        f"version: 1\nscenarios:\n  - name: route\n    start: {{x: 0, y: 0}}\n"
        f"    goal: {{x: 1, y: 1}}\n    goal_tolerance_m: {value}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="goal_tolerance_m"):
        load_config(config_path)


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "true"])
def test_load_config_rejects_invalid_min_feedback_samples(
    tmp_path: Path,
    value: str,
) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text(
        f"version: 1\nscenarios:\n  - name: route\n    start: {{x: 0, y: 0}}\n"
        f"    goal: {{x: 1, y: 1}}\n    min_feedback_samples: {value}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="min_feedback_samples"):
        load_config(config_path)


@pytest.mark.parametrize("map_id", ["", "   ", 42, True])
def test_load_config_rejects_invalid_map_id(tmp_path: Path, map_id: object) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text(
        "\n".join(
            [
                "version: 1",
                "scenarios:",
                "  - name: route",
                f"    map_id: {json.dumps(map_id)}",
                "    start: {x: 0, y: 0}",
                "    goal: {x: 1, y: 1}",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="map_id must be a non-empty string"):
        load_config(config_path)


def test_get_scenario_reads_from_loaded_config(tmp_path: Path) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text(
        """
version: 1
scenarios:
  - name: alpha
    start: {x: 0, y: 0}
    goal: {x: 3, y: 4}
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)
    scenario = get_scenario(config, "alpha")

    assert scenario.goal.x == 3.0
    assert scenario.goal.y == 4.0

    with pytest.raises(ConfigError, match="unknown scenario 'missing'"):
        get_scenario(config, "missing")


def test_load_config_rejects_float_version(tmp_path: Path) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text(
        "version: 1.0\nruntime: auto\nscenarios: []\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="version must be 1"):
        load_config(config_path)


@pytest.mark.parametrize("runtime", ["[]", "{}", "42", "true"])
def test_load_config_rejects_non_string_runtime(tmp_path: Path, runtime: str) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text(
        f"""
version: 1
runtime: {runtime}
scenarios:
  - name: route
    start: {{x: 0, y: 0}}
    goal: {{x: 1, y: 1}}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="runtime must be one of"):
        load_config(config_path)


@pytest.mark.parametrize("value", [".nan", ".inf", "-.inf"])
def test_load_config_rejects_non_finite_pose_values(tmp_path: Path, value: str) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text(
        f"""
version: 1
scenarios:
  - name: route
    start: {{x: {value}, y: 0}}
    goal: {{x: 1, y: 1}}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=r"scenarios\[0\]\.start\.x must be finite"):
        load_config(config_path)


@pytest.mark.parametrize("value", [".nan", ".inf", "-.inf"])
def test_load_config_rejects_non_finite_timeout(tmp_path: Path, value: str) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text(
        f"""
version: 1
scenarios:
  - name: route
    start: {{x: 0, y: 0}}
    goal: {{x: 1, y: 1}}
    timeout_sec: {value}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=r"scenarios\[0\]\.timeout_sec must be finite"):
        load_config(config_path)


@pytest.mark.parametrize(
    ("document", "message"),
    [
        (
            """
version: 1
controller: mppi
scenarios:
  - name: route
    start: {x: 0, y: 0}
    goal: {x: 1, y: 1}
""",
            "config contains unknown keys: 'controller'",
        ),
        (
            """
version: 1
scenarios:
  - name: route
    controller: mppi
    start: {x: 0, y: 0}
    goal: {x: 1, y: 1}
""",
            r"scenarios\[0\] contains unknown keys: 'controller'",
        ),
        (
            """
version: 1
scenarios:
  - name: route
    start: {x: 0, y: 0, z: 0}
    goal: {x: 1, y: 1}
""",
            r"scenarios\[0\]\.start contains unknown keys: 'z'",
        ),
    ],
)
def test_load_config_rejects_unknown_keys(
    tmp_path: Path,
    document: str,
    message: str,
) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text(document.strip(), encoding="utf-8")

    with pytest.raises(ConfigError, match=message):
        load_config(config_path)


@pytest.mark.parametrize(
    "document",
    [
        """
version: 1
runtime: auto
runtime: docker
scenarios:
  - name: route
    start: {x: 0, y: 0}
    goal: {x: 1, y: 1}
""",
        """
version: 1
scenarios:
  - name: route
    name: duplicate
    start: {x: 0, y: 0}
    goal: {x: 1, y: 1}
""",
        """
version: 1
scenarios:
  - name: route
    start: {x: 0, x: 2, y: 0}
    goal: {x: 1, y: 1}
""",
    ],
)
def test_load_config_rejects_duplicate_yaml_keys(tmp_path: Path, document: str) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text(document.strip(), encoding="utf-8")

    with pytest.raises(ConfigError, match="duplicate key"):
        load_config(config_path)


def test_load_config_preserves_yaml_merge_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text(
        """
version: 1
scenarios:
  - name: route
    start: &origin {x: 0, y: 0, yaw: 0}
    goal:
      <<: *origin
      x: 1
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.scenarios[0].start == PoseConfig(x=0.0, y=0.0, yaw=0.0)
    assert config.scenarios[0].goal == PoseConfig(x=1.0, y=0.0, yaw=0.0)
