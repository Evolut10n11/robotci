# Nav2 Loopback example

This is the bundled RobotCI public-alpha example. It uses the same deterministic
Nav2 Loopback runtime exercised by RobotCI CI and contains three navigation
routes with explicit evidence policies.

From a RobotCI source checkout:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .

robotci validate --config examples/nav2-loopback/robotci.yaml
robotci plan --config examples/nav2-loopback/robotci.yaml
robotci doctor
```

Run the suite on Ubuntu 24.04 with ROS2 Jazzy/Nav2:

```bash
robotci run --config examples/nav2-loopback/robotci.yaml --runtime native
```

Or use a working Linux-container Docker backend:

```bash
robotci run --config examples/nav2-loopback/robotci.yaml --runtime docker
```

Because the config is explicit, generated results are anchored under this
example directory:

```text
examples/nav2-loopback/.robotci/
├── suite-result.json
└── results/
```

This example is simulation-only. Do not copy its coordinates into a physical
robot deployment. For a real project, run `robotci-init`, replace the starter
route with coordinates and a stable map identity for that simulator, validate
the plan, and review the first run before capturing a baseline.

See [../../docs/quickstart.md](../../docs/quickstart.md) for the complete
public-alpha workflow.
