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

For CI pipelines or support tooling that should consume the JSON directly instead of creating a file, use `-` as the output destination:

```bash
robotci-support-bundle --output -
```

The command still returns exit code `0` for a PASS bundle and `1` for a FAIL bundle, so the JSON can be piped to another process without losing the readiness verdict.

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
- the same runtime-readiness checks used by `robotci doctor`, with ROS package installation paths redacted;
- config validity, selected runtime, scenario count, and a safe config failure code;
- an overall PASS/FAIL verdict.

When config validation fails, `config.error_code` is one of:

- `config_not_found` — the requested config file does not exist;
- `config_unreadable` — the file exists but could not be read because of an access or I/O failure;
- `config_invalid` — the file was read successfully but does not satisfy RobotCI config validation.

A valid config reports `error_code: null`. These codes are intended for CI/support routing and do not contain local paths, operating-system error text, or parser details.

## What it intentionally does not contain

The bundle does not include:

- repository or project paths;
- ROS package installation prefixes or other local runtime filesystem locations emitted by package discovery;
- scenario names, poses, routes, or maps;
- source code or configuration contents;
- environment variables;
- credentials or tokens;
- bag files, replay files, logs, or simulation artifacts.

Config validation failures are intentionally summarized rather than embedding parser details or local file paths. Run `robotci validate` locally when the detailed config error is needed.

The standalone `robotci-doctor` report remains a local diagnostic and may contain system-level ROS package locations. Use `robotci-support-bundle` when the artifact is intended to be shared outside the machine.

## Pilot workflow

When a pilot setup is blocked:

1. Run `robotci-support-bundle`.
2. Open `.robotci/support-bundle.json` and review it before sharing.
3. Share only that JSON plus a short description of the intended simulator/runtime.
4. Keep source code, maps, secrets, full shell logs, and production robot access private unless the team independently decides otherwise.

This artifact is intended for compatibility triage, not telemetry. RobotCI does not upload it automatically.
