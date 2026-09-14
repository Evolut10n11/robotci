# External pilot target shortlist

This document turns issue #48 from a generic recruitment goal into a concrete first-pass target list. It is based only on public repository signals and is intended for research/qualification before any outreach.

## Selection rules

Prioritize teams that already expose most of the environment RobotCI needs:

- active ROS 2 + Nav2 work;
- simulation or reproducible bringup, preferably Gazebo;
- configuration-heavy navigation where regressions can be subtle;
- public evidence of CI, Docker, multiple robot platforms, or frequent tuning;
- enough project maturity that a repeatable regression gate could save real engineering time.

Do not assume willingness to participate or pay from public activity alone. The pilot still needs a short qualification conversation and a real run on the team's own repository.

## First wave

| Priority | Team / repository | Why it fits RobotCI | Pilot hypothesis | Commercial signal to test |
| --- | --- | --- | --- | --- |
| 1 | `clearpathrobotics/clearpath_nav2_demos` | Actively maintained Jazzy Nav2 + slam_toolbox configurations for multiple Clearpath platforms. Public configs cover many robot models, which makes navigation tuning/regression risk concrete. | Add one repeatable simulated navigation route, save a known-good baseline, then change a Nav2 parameter and gate the candidate. | Whether multi-platform maintainers want shared baselines, policy thresholds, history, or supported/self-hosted CI across robot families. |
| 2 | `RobotnikAutomation/robotnik_simulation` | Active Jazzy simulation repository with Nav2 task/mission launch flows and multiple simulated Robotnik platforms. The repo is close to RobotCI's ideal "simulation before physical robot" workflow. | Wrap one existing Nav2 mission as a RobotCI suite and verify telemetry/regression detection after a navigation/config change. | Whether a commercial robotics vendor values regression evidence, reusable reports and support strongly enough for a paid pilot. |
| 3 | `linorobot/linorobot2` | Mature ROS 2 autonomous mobile robot stack with Nav2, SLAM Toolbox, Gazebo and the same navigation configuration used across simulation and physical robots. Large public user base and many supported hardware variants. | Prove that one Gazebo route can become a stable regression check for common navigation/config changes without changing the existing bringup model. | Whether maintainers/users want easier CI onboarding, reusable baseline packs, hosted result history, or maintained compatibility support. |
| 4 | `rlxai/rbot` | Simulation-first ROS 2 Jazzy + Gazebo Harmonic AMR stack with Docker/workflow structure and explicit autonomy integration. Good design-partner candidate because the whole stack is reproducible and relatively young. | Integrate RobotCI as a lightweight behavior test on one existing simulated navigation path and measure setup friction. | Whether a modern simulation-first project sees enough value in automated behavior gates to adopt RobotCI as part of normal PR validation. |
| 5 | `UTNuclearRobotics/nav2-modular` | Reproducible Docker Nav2 environment supporting multiple real robot platforms (including Husarion Panther and Clearpath Warthog) and selectable sensors. This directly tests portability across heterogeneous deployments. | Run the same RobotCI contract against at least two platform configurations and identify where runtime adapters/config normalization break. | Whether teams with multiple robots/sensors would pay for supported compatibility, self-hosted policies, shared baselines or engineering support. |

## Why these five

The first two are the strongest commercial-design-partner candidates because they are robotics organizations with active Nav2 simulation code. `linorobot2` is the strongest ecosystem/adoption candidate because it has a large installed user base and simulation-to-hardware parity. `rbot` and `nav2-modular` are useful technical validation targets because they stress modern Jazzy/Gazebo and heterogeneous Dockerized deployments respectively.

This cohort intentionally mixes vendor-grade and community/research targets. A vendor conversation gives better willingness-to-pay evidence; community targets expose onboarding and compatibility problems faster.

## Qualification checklist

Before counting a team toward the five-team pilot, confirm all of the following:

- they currently run ROS 2 + Nav2, not only a historical branch;
- there is a simulation/headless path that can run without proprietary maps or production access;
- they can name at least one navigation regression they currently catch manually or late;
- one engineer can spend roughly one focused session trying RobotCI on a real repository;
- they are comfortable sharing only redacted metrics/errors/screenshots if something blocks setup;
- they agree to answer the repeat-use and paid-layer questions after actually using the tool.

## Suggested first experiment

For each accepted pilot team, keep the first integration intentionally small:

1. run `robotci-init` in a disposable branch or test checkout;
2. run `robotci-doctor` and, if needed, `robotci-support-bundle --output -`;
3. configure exactly one deterministic navigation scenario;
4. run it until infrastructure is stable;
5. save the successful result with `robotci-baseline save pilot-known-good`;
6. make or select one real navigation/config change;
7. run the candidate and evaluate `robotci-baseline gate` plus the report/replay usefulness;
8. record setup time, blockers, repeat-use intent, and the strongest requested paid capability.

Do not expand to hosted auth, billing, production robot deployment or proprietary artifact collection during this pilot.

## Outreach order

Start with the top two vendor-grade targets, then one ecosystem target, then the two technical-design-partner targets. Stop broad recruitment once five teams have agreed to a real hands-on session; the goal is depth of evidence, not a large mailing list.

No external message should claim that the target uses or endorses RobotCI. Public repository activity is only a qualification signal.