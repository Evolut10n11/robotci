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
- content digests for file-backed middleware configuration and the implicit
  `DEFAULT_FASTDDS_PROFILES.xml` in the runtime working directory, including
  the `SKIP_DEFAULT_XML` activation control, plus permission-aware ROS security
  keystore walks that fail on unreadable nodes;
- source, sourceless bytecode outside generated cache directories, and
  native-extension digests from both the outer RobotCI runner package and the
  subprocess package when their roots
  differ, plus runtime shell files and any
  top-level source, sourceless bytecode, native-extension module, or complete
  regular or PEP 420 namespace package tree (including data-only resource
  portions) that can shadow or feed ROS imports, including every import candidate
  exposed from explicit distribution roots and every Python root prepended by
  the clean, packaged ROS Jazzy setup; package-managed symlinks record both
  their lexical target and reachable target content (or stable missing state);
- a SHA-256 environment fingerprint and a combined execution fingerprint.

The runner captures metadata before the first attempt and verifies it again
after the final attempt. It fails closed if the environment cannot be inspected
or if any fingerprinted input changes during the suite. Docker metadata is
collected inside one image built before the suite; every scenario uses that
same image without rebuilding. Native execution rebuilds the child environment
from the exact inherited allowlist recorded in provenance: locale, runtime
wrapper, ROS/RCL/RMW/RCUTILS, and supported middleware controls. Unlisted and
Bash startup/function variables are removed, process-level
`LD_AUDIT`/`LD_PRELOAD` injection is rejected, and executable, library, ROS
overlay, setup identity, and Python search paths are rebuilt. The resulting
environment uses a package-managed system `PATH` without mutable local
directories, a fixed hash seed, UTF-8, no user site, and a fresh private
bytecode-cache prefix. Before
application modules load, every checked-in suite workflow enters through the
public CLI, which relaunches itself with a sanitized Python environment and `-S -B -P`. A stdlib-only launcher loads the exact
fingerprinted RobotCI package path without exporting its checkout parent, then
appends audited distribution roots after the standard library. POSIX uses
process replacement so signals and ROS cleanup semantics are preserved;
system/user site hooks, inherited Python controls, sibling checkout modules,
checkout-local generated caches, and the current working directory cannot
affect orchestration. Both runtime Python layers also use `-S -B -P`,
so site/`.pth` startup hooks do not run and the suite cannot mutate or execute
local `__pycache__` files. Explicit dependency paths and the required
`/opt/ros/jazzy/setup.bash` rebuild the import environment. The attempt sources the packaged ROS Jazzy
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
