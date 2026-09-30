from __future__ import annotations

from pathlib import Path

from robotci.config import load_config


def test_public_alpha_nav2_loopback_example_is_valid() -> None:
    example = Path(__file__).parents[1] / "examples" / "nav2-loopback" / "robotci.yaml"
    config = load_config(example)

    assert config.version == 1
    assert config.runtime == "auto"
    assert [scenario.name for scenario in config.scenarios] == [
        "short_route",
        "medium_route",
        "simple_route",
    ]
    assert all(scenario.map_id == "nav2-loopback" for scenario in config.scenarios)
    assert all(scenario.goal_tolerance_m == 0.25 for scenario in config.scenarios)
    assert all(scenario.min_feedback_samples == 1 for scenario in config.scenarios)
