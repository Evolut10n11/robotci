# Real-robot model probe, 2026-10-13

Internal simulation evidence requested by Ivan, not an external M8 pilot or an
announcement that RobotCI's Nav2 schema supports humanoids and manipulators.
Protocol and sources: [experiment](../../experiments/robot_models/README.md).

## First measured execution

- PR #102 head: `47d9a65ae7667a50c98539498a2b0764f042420e`.
- Executed merge ref: `08ab4a7a0bb2058e3d76be9dab062abc4e75ffbf`.
- [Physics workflow](https://github.com/Evolut10n11/robotci/actions/runs/38370553962).
- Artifact: `11798458655`, ZIP SHA-256
  `d678640e139e90777ccd016daa8a8ea08e4961f307930029b63c697baaf22a95`.
- MuJoCo 3.3.7, Python 3.12.15, NumPy 2.2.6, Ubuntu runner, CPU physics.
- Menagerie revision: `0059d4335f8156206f63a35662313385f7ad6d74`.
- Fifteen real integrated episodes, each 3000 steps of 0.002 s. All completed
  without MuJoCo numerical warnings. Three baseline repetitions and two candidate
  repetitions per model had identical sampled qpos within each group.

## Observed results

| Model | Baseline | Candidate (P gain x0.15) | Experimental finding |
| --- | --- | --- | --- |
| Unitree Go2, 12 actuators | Hinge RMSE 0.046214 rad; final base height 0.260725 m | RMSE 0.306222 rad; height 0.164474 m | Tracking qualification lost; substantial crouching, not a numerical failure |
| Unitree G1, 29 actuators | RMSE 0.002817 rad; maximum tilt 2.631553 deg | RMSE 0.032654 rad; tilt 94.639036 deg; final base height 0.083928 m | Posture lost; the simulated humanoid fell |
| Franka Emika Panda, 7 controlled arm hinges + gripper | Hinge RMSE 0.006324 rad | RMSE 0.031721 rad | Tracking error increased about 5.016x |

Metrics came from stepping the physics with a changed controller parameter, not
editing JSON after a run. Model source files remained unchanged. Downloaded ZIP
and per-episode trace hashes were independently checked; all baseline/candidate
repetition qpos arrays were also compared directly, not just their summaries.

Both Unitree model directories contain BSD-3-Clause licenses; Panda contains
Apache-2.0. Original model LICENSE texts travel with the measured artifact.
Menagerie models approximate their real counterparts; no system identification,
hardware accuracy, locomotion, grasping, obstacle navigation or general robustness
is established by six-second posture/servo probes.

## Code/acceptance status at this checkpoint

The physics experiment succeeded. Core CI initially identified two style issues
(an unused loop variable and a 101-character line), corrected without changing
physics or thresholds. Follow-up rendering tracks free-base x/y so the fallen
G1 remains in frame; rendering uses separate mjData. Final head CI is separate
from the first measured execution above.

Interactive Chromium acceptance is a separate script/workflow. It selects and
records an unexpired successful native suite producer, preserving its artifact
identity. It checks real browser controls, 2D/3D, imports and report export.
Its result is not claimed until the browser-summary artifact is inspected.

Remaining Nav2 measured controller-pair acceptance and external M8 evidence stay
open in #99; the separate model-probe comparison does not silently replace them.
