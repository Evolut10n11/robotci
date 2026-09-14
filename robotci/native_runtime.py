from __future__ import annotations

import subprocess
from pathlib import Path

REQUIRED_ROS_PACKAGES = (
    "nav2_bringup",
    "nav2_loopback_sim",
    "nav2_simple_commander",
)
ROS_SETUP = Path("/opt/ros/jazzy/setup.bash")

# Match run_navigation_attempt.sh: require and source the packaged Jazzy
# installation. Do not import ROS in the Python core.
_NATIVE_PROBE = r'''
set -eo pipefail
setup_file="$1"
shift
[ -f "$setup_file" ] || exit 1
source "$setup_file" >/dev/null 2>&1
command -v ros2 >/dev/null 2>&1 || exit 1
[ "${ROS_DISTRO:-}" = "jazzy" ] || exit 1
for package in "$@"; do
  prefix="$(timeout --kill-after=1s 5s ros2 pkg prefix "$package" 2>/dev/null)" || exit 1
  [ -n "$prefix" ] || exit 1
done
'''


def probe_native_ros() -> bool:
    """Check the effective Linux runtime environment, not just an executable."""
    try:
        result = subprocess.run(
            ["bash", "-c", _NATIVE_PROBE, "robotci-native-probe", str(ROS_SETUP),
             *REQUIRED_ROS_PACKAGES],
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0
