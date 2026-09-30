# RobotCI onboarding

For the full external-user flow from installation through baseline gating, start
with [quickstart.md](quickstart.md).

The shortest path for adding RobotCI to an existing ROS2/Nav2 repository is:

```bash
robotci-init
```

This creates a validated `robotci.yaml` in the current directory with one
starter scenario:

```yaml
version: 1
runtime: auto

scenarios:
  - name: smoke_route
    map_id: nav2-loopback
    start:
      x: 0.0
      y: 0.0
      yaw: 0.0
    goal:
      x: 1.0
      y: 0.0
      yaw: 0.0
    timeout_sec: 60
    goal_tolerance_m: 0.25
    min_feedback_samples: 1
```

The generated file is intentionally valid but not target-specific. Before the
first run, replace the starter route with coordinates that are safe in the
target simulator and set `map_id` to a stable map identity.

Then inspect the configuration without starting a runtime:

```bash
robotci validate
robotci plan
robotci doctor
```

Run only after the resolved plan is correct:

```bash
robotci run
```

The initializer never silently overwrites an existing `robotci.yaml`. To
intentionally replace it:

```bash
robotci-init --force
```

To initialize another existing repository without changing the current working
directory:

```bash
robotci-init --project-root ../my-nav2-project
```

The command prints the exact config path and follow-up validation/runtime
commands.

## What the initializer does not do

`robotci-init` does not guess robot-specific coordinates, modify Nav2 launch
files, configure a physical robot, create cloud resources, or certify that a
route is safe. It only creates a deterministic starter RobotCI configuration
that passes RobotCI's own config parser.

The first run should remain simulation-only until the scenario coordinates,
map identity, evidence policy, and runtime integration have been reviewed for
the target environment.
