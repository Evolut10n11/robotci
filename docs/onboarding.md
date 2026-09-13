# RobotCI onboarding

The shortest local-first path for a new ROS2/Nav2 repository is:

```bash
robotci-init
```

This creates a validated `robotci.yaml` in the current directory with one starter scenario:

```yaml
version: 1
runtime: auto

scenarios:
  - name: smoke_route
    start:
      x: 0.0
      y: 0.0
      yaw: 0.0
    goal:
      x: 1.0
      y: 0.0
      yaw: 0.0
    timeout_sec: 60
```

Edit the start and goal coordinates so they match a safe route in your simulation. Then run:

```bash
robotci validate
robotci doctor
robotci run
```

The initializer never silently overwrites an existing `robotci.yaml`. To intentionally replace it:

```bash
robotci-init --force
```

To initialize another existing repository without changing the current working directory:

```bash
robotci-init --project-root path/to/repository
```

The command prints the exact config path and follow-up `validate`, `doctor`, and `run` commands.

## What the initializer does not do

`robotci-init` does not guess robot-specific coordinates, modify Nav2 launch files, configure a physical robot, or create cloud resources. It only creates a deterministic starter RobotCI configuration that already passes RobotCI's own config parser.

The first run should remain simulation-only until the scenario coordinates have been reviewed for the target environment.
