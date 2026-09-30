"""Presentation-only robot profiles, shared by config and Replay v1 readers."""

from typing import Literal

RobotVisualProfile = Literal["rover", "quadruped", "humanoid"]
ROBOT_VISUAL_PROFILES = frozenset({"rover", "quadruped", "humanoid"})
