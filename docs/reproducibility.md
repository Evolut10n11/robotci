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
  isolation, Python-package versions, and the installed transitive dependency
  closure of ROS/Nav2, the selected RMW implementation, and package-managed
  shell/runtime tools;
- a safe whitelist of inherited ROS/RMW behavior, RCUTILS logging, middleware,
  locale, and runtime-wrapper variables, stored only as value SHA-256 digests;
- content digests for file-backed middleware configuration and explicit,
  permission-aware ROS security keystore walks that fail on unreadable nodes;
- source digests of both the outer RobotCI runner package and the subprocess
  package when they come from different roots, plus runtime shell files;
- a SHA-256 environment fingerprint and a combined execution fingerprint.

The runner captures metadata before the first attempt and verifies it again
after the final attempt. It fails closed if the environment cannot be inspected
or if any fingerprinted input changes during the suite. Docker metadata is
collected inside one image built before the suite; every scenario uses that
same image without rebuilding. Native execution strips Bash startup/function injection variables, rejects
process-level `LD_AUDIT`/`LD_PRELOAD` injection, drops inherited executable,
library, ROS overlay, setup identity, and Python search paths, and sets a
package-managed system `PATH` without mutable local directories, a fixed hash
seed, UTF-8, and no user site. The required `/opt/ros/jazzy/setup.bash` then
rebuilds every setup-owned ROS path and identity. The cleanup helper uses Python
isolated mode and adds
the fingerprinted package only after interpreter startup, so checkout-level
`sitecustomize.py` hooks cannot run. The attempt sources the packaged ROS Jazzy
setup while Python resolves RobotCI from the fingerprinted runtime checkout. It honors the
runner-selected Python across both shell layers and fingerprints the checkout
package when it shadows an installed distribution. A process running inside the image is recorded as the Docker
runtime even though it invokes the native adapter internally.

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
