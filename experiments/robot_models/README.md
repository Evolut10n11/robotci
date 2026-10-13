# Pinned real-robot model probes

Requested by Ivan on 2026-10-13. This is a bounded simulation experiment, not a
production adapter, hardware test, walking policy or M8 external-team evidence.
It does not feed unsupported joint metrics into RobotCI's Nav2 result schema.

Models come from Google DeepMind MuJoCo Menagerie, fixed at commit
`0059d4335f8156206f63a35662313385f7ad6d74`:

- `unitree_go2`: twelve-actuator quadruped; joint-space PD holds its home posture.
- `unitree_g1`: humanoid with upstream position servos; no balance/locomotion policy.
- `franka_emika_panda`: fixed-base arm and gripper; first arm joint moves 0.25 rad.

Source: https://github.com/google-deepmind/mujoco_menagerie/tree/0059d4335f8156206f63a35662313385f7ad6d74
Each model's original LICENSE is retained in the results. Upstream meshes,
inertias, collision geometry, gravity and integration timestep are not replaced.

## Protocol fixed before observing results

Five six-second episodes per model: three baseline repetitions and two candidates.
The only candidate change is proportional servo gain multiplied by 0.15; damping,
initial keyframe, target trajectory, physics, model assets and applied force stay
fixed. Go2 motor control uses kp=80 and kd=4; position actuators retain their
upstream gains except for that candidate P multiplier. Free-base robots receive
the same 0.1-body-weight x-axis force during simulation seconds 2.0 to 2.2.

Measure real integrated joint error after one second, base height and tilt,
joint-limit overshoot, contact counts, engine warnings and qpos/qvel/control traces.
Posture/servo qualification requires finite completed integration without engine
warnings, height >=60% of starting height, tilt <=60 degrees, hinge RMSE <=0.25 rad
and joint-limit overshoot <=0.10 rad. Fixed-base arms have no base-height/tilt test.
Compare baseline repeats at absolute qpos tolerance 1e-10 in the same process and
machine; this is not a cross-platform bitwise reproducibility claim.

A baseline that falls or tracks poorly yields BASELINE_NOT_QUALIFIED, not a false
regression claim. Other comparisons flag lost qualification, numerical error, or
RMSE growth exceeding both 25% and 0.01 rad. These are experimental thresholds,
not calibrated physical-robot acceptance criteria or the official Nav2 gate.

## Execution

The `Robot Model Probes` GitHub workflow installs optional dependencies on its
isolated Ubuntu runner, checks out only the pinned model directories, and emits
JSON, original license text, compressed measured traces and rendered videos.
Exit 0 means every experiment produced a complete record, not that every robot
passed its posture test. Read episode verdicts and the per-model finding.

From a checkout with the pinned Menagerie repository available at `artifacts/model-source`:

```powershell
python -m pip install -r experiments/robot_models/requirements.txt
python experiments/robot_models/probe.py --models-root artifacts/model-source --output artifacts/model-probe
```

Add `--render` with a working MuJoCo OpenGL backend. Render errors are reported
separately from physics. Evidence directories must be new; source files are hashed
before/after and never edited. This script does not launch ROS or access hardware.

Completion goal #99 retains its independent Nav2 controller-pair and browser
acceptance requirements. Success here does not silently close either requirement.
