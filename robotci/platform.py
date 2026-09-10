from __future__ import annotations

import platform as stdlib_platform
from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformInfo:
    system: str
    core_supported: bool
    ros_runtime_supported: bool

    @property
    def summary(self) -> str:
        if self.ros_runtime_supported:
            return f"{self.system}: RobotCI core and ROS runtime supported"
        if self.core_supported:
            return f"{self.system}: RobotCI core supported; ROS runtime requires Linux"
        return f"{self.system}: platform is not officially supported"


def current_platform(system: str | None = None) -> PlatformInfo:
    detected = (system or stdlib_platform.system()).strip() or "Unknown"

    return PlatformInfo(
        system=detected,
        core_supported=detected in {"Windows", "Linux"},
        ros_runtime_supported=detected == "Linux",
    )
