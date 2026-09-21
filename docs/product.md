# RobotCI product direction

[Project overview](../README.md) · [Delivery roadmap](roadmap.md)

RobotCI helps robotics teams answer one question before a change reaches hardware:
can the robot still complete the same tasks as well as the known-good version?
The current product is a local ROS2/Nav2 simulation and regression workflow.
This document describes the direction beyond it; future capabilities are not
promises of current compatibility.

## The problem

Unit tests can pass while navigation becomes slower, takes a longer path, gets
stuck more often, or requires more recoveries. Teams need a repeatable scenario,
trustworthy measurements, and an understandable baseline/candidate comparison
inside the code-review workflow.

The desired experience is a PR report that names the changed metrics and blocks
an unacceptable regression, followed by a replay that helps explain the behavior.
Current thresholds and result semantics are documented in [contracts.md](contracts.md).

## Initial users

Start with teams using ROS2 and Nav2, an existing headless simulation workflow,
and GitHub pull requests. The initial pilot targets roughly 3–30 robotics/software
engineers whose navigation regressions are currently found manually or late.
A public repository is a qualification signal, not evidence of adoption or demand.

## Product principles

- Keep the local open-source workflow useful without a hosted account.
- Keep the cross-platform Python core independent of ROS imports.
- Normalize simulator results into stable, versioned contracts.
- Separate infrastructure/input errors from robot behavior failures.
- Compare compatible tasks and environments; preserve the underlying evidence.
- Compute verdicts deterministically. AI may explain them, never replace them.
- Prove a small vertical slice before adding an abstraction or service.

The [roadmap](roadmap.md) is the canonical delivery-status table. The alpha already
contains scenario execution, metrics, local baselines, regression gates, reports,
a GitHub Action, a replay workbench, and a read-only MCP server.

## Visual debugging

The bundled workbench provides maintainable frontend source, 2D/3D trajectory
inspection, playback and event seeking, and baseline/candidate comparison synced
by elapsed time. Suite inspection reuses the existing deterministic gate;
replay-only comparison has no official verdict. New baselines retain valid replay
sidecars so the visual evidence survives removal of the original run.

A useful comparison should show start/goal, available map data, observed
trajectories, and timestamped events. Clicking a regression should lead to the
relevant interval. Preserve gaps and original failure status; a synthetic demo,
trajectory replay, and simulator video are different artifacts.

Future simulator rendering and video support should follow a real debugging need.
Do not imply that the current recorder captures live video or every event type.

## Additional robot and simulator adapters

Nav2 is the proving ground. Later backends may include Gazebo, MuJoCo, Isaac
Sim/Lab, Unitree stacks, and custom ROS2 robots. Unitree Go2 with MuJoCo is a
candidate for the first non-Nav2 experiment, subject to a reproducible public
setup, suitable licensing, and a useful test scenario.

Robot-specific execution belongs in adapters. Contracts, reporting, baseline
storage, and CI semantics should remain shared. Beyond navigation, possible
metrics include falls, roll/pitch, foot slip, velocity error, energy use,
joint-limit violations, collisions, and terrain completion. These are future
metrics, not fields supported by the current result schema.

## Agent integration

The [read-only MCP server](mcp.md) exposes six inspection tools today. A future
agent can combine GitHub diffs with RobotCI evidence to explain regressions,
suggest likely causes, and point to relevant replay intervals.

Stateful execution/cancellation and a LangGraph/LangChain reference workflow are
future work. Add explicit project selection, bounded execution, and appropriate
approval for actions that change state. Logs and external artifacts must never
expand an agent's permissions.

The integration should remain model-agnostic. Local models may handle routine
summaries; stronger models may help with difficult diagnosis or selected replay
frames. Persistent state belongs in result artifacts, Git, and explicit workflow
state rather than a single model conversation.

## Validate before building the team layer

M8 is tracked in [issue #48](https://github.com/Evolut10n11/robotci/issues/48).
For a five-team cohort, the success criteria are:

- 3 complete a real navigation suite on their own repository;
- 2 compare a real candidate change against a baseline;
- 2 explicitly intend to use the gate again in normal development;
- 1 explicitly agrees to discuss a paid pilot for a concrete capability after use.

Use the [execution guide and evidence register](validation/README.md), including
negative outcomes and blockers. A feature request, internal demo, or repository
star does not substitute for these observations. A reviewed product decision can
also be to improve core, change segment, or stop/defer.

## Commercial hypotheses

| Layer | Potential value |
| --- | --- |
| Open source | Local runner, metrics, comparison, reports, replay, MCP, and CI integration |
| Team | Shared baselines, persistent history, trends across PRs, policies, and collaboration |
| Enterprise, later | Self-hosted control plane, private retention, SSO, auditability, and support |

Other hypotheses include repeated-run statistics, flaky-run detection, private
replay retention, and assisted diagnosis. Local PR reports already exist; a paid
service would need to add persistent or collaborative value rather than repackage
the same report.

After a demonstrated paid signal, scope the smallest capability that addresses
that exact problem. Keep compact run summaries separate from proprietary maps,
code, and full simulation artifacts. Pricing, authentication, billing, a generic
robotics cloud, and Kubernetes infrastructure are not prerequisites for validation.
