from __future__ import annotations

import pytest

from robotci.scenarios import get_scenario, scenario_names


def test_builtin_scenarios_are_stable_and_share_m1_origin() -> None:
    names = scenario_names()

    assert names == ("short_route", "medium_route", "simple_route")
    for name in names:
        scenario = get_scenario(name)
        assert scenario.name == name
        assert scenario.start.x == 0.0
        assert scenario.start.y == 0.0
        assert scenario.start.yaw == 0.0


def test_unknown_scenario_reports_supported_names() -> None:
    with pytest.raises(ValueError, match="short_route, medium_route, simple_route"):
        get_scenario("missing_route")
