from __future__ import annotations

import json

from robotci.results import Pose2D, ScenarioResult, write_result


def test_write_result_creates_portable_json(tmp_path) -> None:
    result = ScenarioResult(
        scenario="simple_route",
        status="PASS",
        duration_sec=12.345,
        start=Pose2D(x=0.0, y=0.0, yaw=0.0),
        goal=Pose2D(x=17.86, y=-0.77, yaw=0.0),
        navigation_result="SUCCEEDED",
    )

    output = tmp_path / "nested" / "result.json"
    written = write_result(result, output)

    assert written == output
    assert written.exists()

    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload == {
        "duration_sec": 12.345,
        "goal": {"x": 17.86, "y": -0.77, "yaw": 0.0},
        "navigation_result": "SUCCEEDED",
        "scenario": "simple_route",
        "start": {"x": 0.0, "y": 0.0, "yaw": 0.0},
        "status": "PASS",
    }
