FROM ros:jazzy-ros-base-noble

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3-venv \
        ros-jazzy-navigation2 \
        ros-jazzy-nav2-bringup \
        ros-jazzy-nav2-loopback-sim \
        ros-jazzy-nav2-simple-commander \
        ros-jazzy-nav2-minimal-tb4-description \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY pyproject.toml README.md LICENSE robotci.yaml ./
COPY robotci ./robotci

RUN python3 -m venv --system-site-packages /opt/robotci-venv \
    && /opt/robotci-venv/bin/python -m pip install --upgrade pip \
    && /opt/robotci-venv/bin/python -m pip install .

ENV PATH="/opt/robotci-venv/bin:${PATH}"

COPY scripts ./scripts

CMD ["robotci", "run", "--runtime", "native", "--config", "/workspace/robotci.yaml", "--output", "/workspace/artifacts/suite-result.json"]
