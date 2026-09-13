from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from robotci.metrics import NavigationMetrics
from robotci.results import Pose2D, ScenarioStatus


class ReplayRecorder:
    """Collect lightweight navigation telemetry for Replay v1."""

    def __init__(
        self,
        *,
        scenario: str,
        start: Pose2D,
        goal: Pose2D,
        started_at: float,
        runtime: str = "ros2_nav2",
        robot_type: str = "generic_mobile_base",
    ) -> None:
        self.scenario = scenario
        self.start = start
        self.goal = goal
        self.started_at = started_at
        self.runtime = runtime
        self.robot_type = robot_type
        self._samples: list[dict[str, Any]] = [self._sample(0.0, start.x, start.y, start.yaw)]

    @staticmethod
    def _sample(t: float, x: float, y: float, yaw: float) -> dict[str, Any]:
        return {
            "t": round(max(0.0, t), 3),
            "position": {"x": float(x), "y": float(y), "z": 0.0},
            "orientation": {"yaw": float(yaw)},
        }

    def record(self, *, x: float, y: float, yaw: float, now: float) -> None:
        """Append one fresh navigation feedback pose."""
        values = (x, y, yaw, now)
        if not all(math.isfinite(value) for value in values):
            return

        elapsed = max(0.0, now - self.started_at)
        self._samples.append(self._sample(elapsed, x, y, yaw))

    def build(
        self,
        *,
        status: ScenarioStatus,
        duration_sec: float,
        metrics: NavigationMetrics,
        navigation_result: str,
    ) -> dict[str, Any]:
        """Build a self-contained Replay v1 payload."""
        last_t = float(self._samples[-1]["t"])
        duration = round(max(0.001, float(duration_sec), last_t), 3)

        samples = list(self._samples)
        if len(samples) == 1:
            samples.append(
                self._sample(
                    duration,
                    self.start.x,
                    self.start.y,
                    self.start.yaw,
                )
            )

        viewer_status = "PASS" if status == "PASS" else "FAIL"
        final_event = "GOAL" if status == "PASS" else "FAIL"
        return {
            "schema_version": 1,
            "scenario": self.scenario,
            "status": viewer_status,
            "result_status": status,
            "runtime": self.runtime,
            "duration_sec": duration,
            "robot": {"type": self.robot_type},
            "world": {
                "frame": "map",
                "goal": {"x": self.goal.x, "y": self.goal.y, "z": 0.0},
            },
            "samples": samples,
            "metrics": {
                "duration_sec": duration,
                "path_length_m": metrics.path_length_m,
                "distance_to_goal_m": metrics.distance_to_goal_m,
                "stuck_events": metrics.stuck_events,
                "recoveries": metrics.recoveries,
            },
            "events": [
                {"t": 0.0, "type": "START", "message": "Navigation started"},
                {
                    "t": duration,
                    "type": final_event,
                    "message": navigation_result,
                },
            ],
        }


def default_replay_path(result_path: str | Path) -> Path:
    """Return the replay artifact path associated with a scenario result."""
    path = Path(result_path)
    if path.suffix:
        return path.with_name(f"{path.stem}.replay{path.suffix}")
    return path.with_name(f"{path.name}.replay.json")


def write_replay(payload: dict[str, Any], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path
