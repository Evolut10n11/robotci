# Reproducible suite execution

M5 makes the environment used by a suite part of the comparison contract. A
successful navigation result is not comparable with a baseline merely because
the scenario name matches.

Every newly written `suite-result.json` uses suite schema version 1 and contains
an `execution` object with:

- the effective runtime (`native` or `docker`);
- the versioned `ros2-nav2-jazzy-loopback-v1` runtime contract;
- a canonical SHA-256 fingerprint of scenario order, poses, map, effective
  timeouts, and evidence policies;
- the actual Ubuntu, architecture, Python, ROS distribution, container
  isolation, Python-package, and ROS/Nav2 Debian-package versions;
- a source digest of the executable RobotCI Python and runtime shell files;
- a SHA-256 environment fingerprint and a combined execution fingerprint.

The runner captures metadata after the runtime attempts and fails closed if the
environment cannot be inspected. Docker metadata is collected inside the built
image, not from the host. A process running inside the image is recorded as the
Docker runtime even though it invokes the native adapter internally.

Baseline capture validates the complete contract before copying artifacts.
Suite regression comparison requires exact execution fingerprints before it
loads scenario metrics. Changed task inputs, host/container mode, Python patch
versions, or ROS/Nav2 package drift therefore produce an input error instead of
a misleading `PASS`, `REGRESSION`, or robot-behavior `FAIL`.

For repeatable gates, capture the baseline and candidate with the same RobotCI
runtime image or the same provisioned native environment. Rebuild both when an
intentional runtime upgrade changes the fingerprint. Existing pre-M5 suite
files have no trustworthy execution identity and must be rerun before baseline
capture or comparison.
