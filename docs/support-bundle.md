# Pilot support bundle

Use the support bundle when a RobotCI pilot is blocked during setup and the team needs to share diagnostics without sending its repository, maps, scenario names, credentials, environment variables, or simulation artifacts.

## Create the bundle

After installing RobotCI, run:

```bash
robotci-support-bundle
```

The default output is:

```text
.robotci/support-bundle.json
```

For inventory or an early compatibility discussion where a working runtime is not required yet:

```bash
robotci-support-bundle --runtime-optional
```

When the pilot specifically requires native ROS2 Jazzy/Nav2 and Docker fallback must not satisfy readiness:

```bash
robotci-support-bundle --require-ros
```

A custom config and destination can be selected explicitly:

```bash
robotci-support-bundle --config robotci.yaml --output .robotci/support-bundle.json
```

The module form remains available for source checkouts or environments where console scripts are not on `PATH`:

```bash
python -m robotci.support_bundle --runtime-optional
```

For machine-readable runtime readiness without config validation, use:

```bash
robotci-doctor
robotci-doctor --runtime-optional
robotci-doctor --require-ros --output .robotci/doctor.json
```

## What it contains

The JSON bundle is schema-versioned and contains only compact setup information:

- RobotCI version;
- operating-system family and Python version;
- the same runtime-readiness checks used by `robotci doctor`;
- config validity, selected runtime, and scenario count;
- an overall PASS/FAIL verdict.

## What it intentionally does not contain

The bundle does not include:

- repository or project paths;
- scenario names, poses, routes, or maps;
- source code or configuration contents;
- environment variables;
- credentials or tokens;
- bag files, replay files, logs, or simulation artifacts.

Config validation failures are intentionally summarized rather than embedding parser details or local file paths. Run `robotci validate` locally when the detailed config error is needed.

Doctor diagnostics may identify installed runtime components and system-level ROS package locations. Review the JSON before sharing it if the organization treats host/runtime inventory as sensitive.

## Pilot workflow

When a pilot setup is blocked:

1. Run `robotci-support-bundle`.
2. Open `.robotci/support-bundle.json` and review it before sharing.
3. Share only that JSON plus a short description of the intended simulator/runtime.
4. Keep source code, maps, secrets, full shell logs, and production robot access private unless the team independently decides otherwise.

This artifact is intended for compatibility triage, not telemetry. RobotCI does not upload it automatically.
