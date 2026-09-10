#!/usr/bin/env bash
set -Eeo pipefail

if [ ! -f /etc/os-release ]; then
  echo "RobotCI bootstrap supports Ubuntu 24.04 only."
  exit 1
fi

# shellcheck disable=SC1091
source /etc/os-release

if [ "${ID:-}" != "ubuntu" ] || [ "${VERSION_ID:-}" != "24.04" ]; then
  echo "RobotCI bootstrap supports Ubuntu 24.04 only."
  echo "Detected: ${PRETTY_NAME:-unknown system}"
  exit 1
fi

sudo apt-get update
sudo apt-get install -y software-properties-common curl python3-venv
sudo add-apt-repository -y universe

if [ ! -f /etc/apt/sources.list.d/ros2.sources ] \
  && [ ! -f /etc/apt/sources.list.d/ros2.list ]; then
  ROS_APT_SOURCE_VERSION="$(
    curl -fsSL https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest \
      | grep -F '"tag_name"' \
      | awk -F'"' '{print $4}'
  )"

  curl -fsSL -o /tmp/ros2-apt-source.deb \
    "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.noble_all.deb"
  sudo dpkg -i /tmp/ros2-apt-source.deb
fi

sudo apt-get update
sudo apt-get install -y \
  ros-jazzy-ros-base \
  ros-jazzy-navigation2 \
  ros-jazzy-nav2-bringup \
  ros-jazzy-nav2-loopback-sim \
  ros-jazzy-nav2-simple-commander \
  ros-jazzy-nav2-minimal-tb4-description

python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"

cat <<'EOF'

RobotCI Ubuntu environment is ready.

Activate the environment and run the built-in suite with:

  source .venv/bin/activate
  robotci run --runtime native

Run one scenario while debugging with:

  robotci run --runtime native --scenario simple_route

Core checks:

  .venv/bin/python -m pytest -vv
  .venv/bin/ruff check .

EOF
