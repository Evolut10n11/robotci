# 3D Replay Viewer

RobotCI includes a local browser-based 3D viewer for deterministic navigation replays.

## Quick start

Open the built-in deterministic demo:

```bash
robotci view --demo
```

Open a recorded Replay v1 artifact:

```bash
robotci view --replay path/to/replay.json
```

By default the viewer binds to `127.0.0.1:8765` and opens the browser automatically. Use `--no-open` for headless/manual use, or override `--host` and `--port` when needed.

## Record a real Nav2 run

A single-scenario `robotci run` now records fresh Nav2 feedback poses automatically. The replay is written beside the normal result using the `.replay.json` suffix.

```bash
robotci run --scenario simple_route
robotci view --replay .robotci/result.replay.json
```

With a custom result path, the replay follows the same location:

```bash
robotci run --scenario simple_route --output artifacts/run-42.json
robotci view --replay artifacts/run-42.replay.json
```

The behavior is the same for native and Docker runtimes. Docker runs copy the replay out of the container beside the requested host result. Suite runs produce one replay per scenario under the suite `results/` directory, for example:

```bash
robotci run
robotci view --replay .robotci/results/simple_route.replay.json
```

## Replay v1

The viewer reads the replay from `GET /api/replay`. A Replay v1 document contains:

- `schema_version`: must be `1`.
- `scenario`: human-readable scenario identifier.
- `status`: viewer verdict, `PASS` or `FAIL`.
- `result_status`: original RobotCI verdict (`PASS`, `FAIL`, `TIMEOUT`, or `INFRA_ERROR`) when emitted by the runtime recorder.
- `runtime`: runtime/backend label.
- `duration_sec`: total replay duration.
- `robot.type`: robot visualization type. Unknown types fall back to the generic mobile base.
- `world.frame`: coordinate frame label.
- `world.goal`: `{x, y, z}` goal position in meters.
- `samples`: ordered timestamped poses with `{x, y, z}` and yaw.
- `metrics`: duration, path length, distance to goal, stuck-event count, and recovery count.
- `events`: timestamped `START`, `REPLAN`, `STUCK`, `RECOVERY`, `GOAL`, or `FAIL` events.

Minimal shape:

```json
{
  "schema_version": 1,
  "scenario": "simple_route",
  "status": "PASS",
  "result_status": "PASS",
  "runtime": "ros2_nav2",
  "duration_sec": 2.0,
  "robot": {"type": "generic_mobile_base"},
  "world": {
    "frame": "map",
    "goal": {"x": 1.0, "y": 0.0, "z": 0.0}
  },
  "samples": [
    {
      "t": 0.0,
      "position": {"x": 0.0, "y": 0.0, "z": 0.0},
      "orientation": {"yaw": 0.0}
    },
    {
      "t": 2.0,
      "position": {"x": 1.0, "y": 0.0, "z": 0.0},
      "orientation": {"yaw": 0.0}
    }
  ],
  "metrics": {
    "duration_sec": 2.0,
    "path_length_m": 1.0,
    "distance_to_goal_m": 0.0,
    "stuck_events": 0,
    "recoveries": 0
  },
  "events": [
    {"t": 0.0, "type": "START", "message": "Navigation started"},
    {"t": 2.0, "type": "GOAL", "message": "Goal reached"}
  ]
}
```

RobotCI validates the file before starting the local server so malformed or unsupported replay data fails fast in the CLI rather than inside the browser.

## Local endpoints

- `GET /` serves the bundled viewer.
- `GET /api/replay` serves the selected replay JSON.
- `GET /healthz` returns a small health response for smoke tests.

The default bind address is loopback-only. No external service or cloud backend is required.
