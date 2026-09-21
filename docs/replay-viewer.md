# Replay workbench

[Руководство на русском](replay-viewer.ru.md)

Inspect recorded robot behavior, compare baseline and candidate trajectories, and
read the deterministic suite gate in one local workspace. All assets are bundled;
no cloud service, account, or Node.js installation is required to use the viewer.
The interface is in Russian. JSON contracts, scenario identifiers, and exported
evidence retain their original values; presentation does not change gate decisions.

![Replay workbench with synchronized synthetic recordings](assets/replay-workbench.jpg)

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
If another project uses that port, use `--port 8766` or `--port 0` to request a
free port. The CLI prints the actual bound URL after the server starts.

## Compare recordings or suites

For a visual comparison of two Replay v1 files:

```bash
robotci view --replay candidate.replay.json --baseline baseline.replay.json
```

You can also choose **Открыть записи** in the browser. Files stay in the browser
and are not uploaded. Imports are limited to 32 MiB and 250,000 pose samples per
file. Invalid numbers, duplicate JSON keys, unsupported statuses, and unordered
or out-of-range timestamps are rejected before the workspace changes.

For the official regression gate, open validated suite results:

```bash
robotci view --suite .robotci/suite-result.json --baseline-name main-nav
```

The named baseline is read from `.robotci/baselines`; `--baseline-store` selects
another store. Alternatively, pass the baseline suite file directly:

```bash
robotci view --suite .robotci/suite-result.json --baseline-suite .robotci/baselines/main-nav/suite-result.json
```

`--baseline-name` and `--baseline-suite` are mutually exclusive. Both require
`--suite`; `--baseline-store` requires `--baseline-name`. These options only read
the saved evidence and never replace or create a baseline.

Use `--scenario simple_route` to select a scenario initially. The viewer delegates
the gate to the same comparison engine as `robotci-suite-gate`, including task,
execution, and telemetry compatibility checks. Its default policy allows +10%
duration, +10% path length, +0.1 m final goal distance, and no additional stuck or
recovery events. Pass the corresponding `--max-*-increase*` flags from
`robotci view --help` to match your CI policy. Opening a viewer never blocks CI;
use the gate commands for blocking exit codes.

| Evidence | What the viewer reports |
| --- | --- |
| Compatible suite pair | Official PASS/REGRESSION, findings, policy limits, and JSON export |
| Replay pair | Visual comparison and metric differences; no gate verdict |
| Incompatible suite pair | Available recordings/metrics and why the gate cannot be evaluated |
| Old result without a replay | Metrics and gate remain available; trajectory is explicitly unavailable |
| Synthetic demo | Clearly marked sample data; no gate verdict |

New baseline captures preserve valid replay sidecars. When opening a suite, a
sidecar must agree with its result's scenario, status, duration, start, goal,
frame (when available), and metrics. A stale or malformed sidecar is withheld;
it cannot replace the suite evidence used by the gate. These consistency checks
are not a cryptographic binding between a trajectory and a result.

## Controls and interpretation

- **Просмотр / Сравнение:** inspect the candidate or overlay an aligned baseline.
- **Вид сверху / 3D / Вписать:** pan, zoom, orbit, and reset the camera. 3D requires
  WebGL; the top view remains usable without it.
- **Playback:** play/pause, seek, 0.25×–4× speed, loop, and previous/next event.
- **Events:** select a marker or log entry to jump to its recorded timestamp.
- **Inspector:** interpolated candidate pose at the playhead, plus final run metrics.
- **Export:** download the official gate JSON, or the candidate Replay v1 file
  when no gate is available.

The timeline uses elapsed seconds, not normalized progress. Each trajectory
holds its final recorded pose after its last sample. Sampling is interpolated
between recorded poses, so it does not reconstruct unobserved behavior. Long
trajectories are reduced for drawing only; the original samples remain available
for pose lookup and export. The event list displays the first 1,000 events of a
large recording; previous/next navigation still considers every recorded event.

Different scenarios, coordinate frames, start positions, or goal positions disable
the overlay and metric deltas. Spatial alignment alone does not establish the
provenance required for an official regression verdict.

Press **?** for shortcuts. **Space** plays/pauses, **← / →** seek one second,
**[ / ]** select events, **Home / End** select the bounds, **F** fits the camera,
and **O** opens files. Russian-layout equivalents **Х / Ъ**, **А**, and **Щ**
also work. Shortcuts do not intercept form controls. Playback pauses
when the tab is hidden and when the scenario or source changes.

The current runtime recorder emits start and terminal events. Metric counts do
not imply that every stuck/recovery event has a timestamp; the viewer never
invents those timestamps. This is a trajectory viewer, not a simulator, map
renderer, live robot controller, or video recording.

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

The viewer consumes a session from `GET /api/session`. The original
`GET /api/replay` endpoint remains available for the initially selected candidate
recording. A Replay v1 document contains:

- `schema_version`: must be `1`.
- `scenario`: human-readable scenario identifier.
- `status`: recorded execution outcome, `PASS` or `FAIL` (not a regression verdict).
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
- `GET /api/session` serves the read-only workspace, scenarios, optional replays,
  and optional suite gate report.
- `GET /api/replay` serves the initially selected candidate replay, or 404 when
  that result has no trajectory.
- `GET /healthz` returns a small health response for smoke tests.

The default bind address is loopback-only. No external service or cloud backend is required.
