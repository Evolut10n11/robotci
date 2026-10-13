"""Real MuJoCo rollouts of pinned robot models; NOT a Nav2 result adapter.

No hardware, networks, training or edited output metrics. Only the proportional
controller gain changes between baseline and candidate. An experiment can finish
successfully while a model's posture test fails; see each episode's verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
from pathlib import Path

MENAGERIE_SHA = "0059d4335f8156206f63a35662313385f7ad6d74"
MODELS = ("unitree_go2", "unitree_g1", "franka_emika_panda")
DURATION = 6.0
GAIN_SCALE = 0.15


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(root: Path) -> dict[str, str]:
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if any(path.is_symlink() for path in root.rglob("*")):
        raise ValueError("model snapshots must not contain symlinks")
    return {path.relative_to(root).as_posix(): digest(path) for path in files}


def qualified(metrics: dict) -> bool:
    return (
        metrics["engine_valid"]
        and metrics["min_base_height_ratio"] >= 0.60
        and metrics["max_base_tilt_deg"] <= 60.0
        and metrics["joint_rmse_rad"] <= 0.25
        and metrics["max_joint_limit_violation_rad"] <= 0.10
    )


def compare(baseline: dict, candidate: dict, repeatable: bool) -> str:
    if not repeatable or not qualified(baseline):
        return "BASELINE_NOT_QUALIFIED"
    if not candidate["engine_valid"]:
        return "CANDIDATE_NUMERICAL_ERROR"
    if not qualified(candidate):
        return "DETECTED_POSTURE_OR_TRACKING_LOSS"
    error = baseline["joint_rmse_rad"]
    threshold = max(error * 1.25, error + 0.01)
    return (
        "DETECTED_TRACKING_REGRESSION"
        if candidate["joint_rmse_rad"] > threshold
        else "NO_REGRESSION_AT_SELECTED_THRESHOLDS"
    )


def episode(scene: Path, out: Path, label: str, gain_scale: float, render: bool) -> tuple:
    import imageio.v2 as imageio
    import mujoco
    import numpy as np
    from PIL import Image, ImageDraw

    model = mujoco.MjModel.from_xml_path(str(scene))
    data = mujoco.MjData(model)
    if model.nkey:
        mujoco.mj_resetDataKeyframe(model, data, 0)
    else:
        mujoco.mj_resetData(model, data)
    mujoco.mj_forward(model, data)
    initial_qpos, initial_ctrl = data.qpos.copy(), data.ctrl.copy()
    free = np.flatnonzero(model.jnt_type == mujoco.mjtJoint.mjJNT_FREE)
    base_adr = int(model.jnt_qposadr[free[0]]) if len(free) else None
    base_body = int(model.jnt_bodyid[free[0]]) if len(free) else None
    height = float(initial_qpos[base_adr + 2]) if base_adr is not None else 1.0
    mappings = []
    for actuator in range(model.nu):
        if model.actuator_trntype[actuator] != mujoco.mjtTrn.mjTRN_JOINT:
            continue  # The coupled gripper keeps the upstream keyframe control.
        joint = int(model.actuator_trnid[actuator, 0])
        if model.jnt_type[joint] != mujoco.mjtJoint.mjJNT_HINGE:
            continue
        qadr, vadr = int(model.jnt_qposadr[joint]), int(model.jnt_dofadr[joint])
        position = model.actuator_biastype[actuator] == mujoco.mjtBias.mjBIAS_AFFINE
        if position:
            if model.actuator_biasprm[actuator, 1] >= 0:
                raise ValueError("unsupported affine actuator, expected a position servo")
            # Scale P gain and position feedback, not damping or the target.
            model.actuator_gainprm[actuator, 0] *= gain_scale
            model.actuator_biasprm[actuator, 1] *= gain_scale
        elif model.actuator_biastype[actuator] != mujoco.mjtBias.mjBIAS_NONE:
            raise ValueError("unsupported actuator bias")
        mappings.append((actuator, joint, qadr, vadr, bool(position)))
    if not mappings or height <= 0:
        raise ValueError("expected actuated hinge joints and a valid initial pose")
    qindices = [entry[2] for entry in mappings]
    dt = float(model.opt.timestep)
    if not math.isfinite(dt) or dt <= 0:
        raise ValueError("invalid timestep")
    count = round(DURATION / dt)
    if count < 1 or count > 100000:
        raise ValueError("unsupported simulation step budget")
    sample_every, frame_every = max(1, round(0.05 / dt)), max(1, round(0.1 / dt))
    trace, velocities, controls, times, errors = [], [], [], [], []
    min_ratio, max_tilt, max_violation, max_contacts = 1.0, 0.0, 0.0, 0
    finite = True
    renderer = writer = None
    render_error = None
    render_data = mujoco.MjData(model)  # Never forward/render the measured data.
    if render:
        try:
            renderer = mujoco.Renderer(model, height=480, width=640)
            writer = imageio.get_writer(str(out / f"{label}.mp4"), fps=10)
        except Exception as exc:
            render_error = f"{type(exc).__name__}: {exc}"
    camera = mujoco.MjvCamera()
    mujoco.mjv_defaultCamera(camera)
    camera.lookat[:] = (0.0, 0.0, height * 0.55 if base_adr is not None else 0.4)
    camera.distance = 2.5 if scene.parent.name == "unitree_g1" else 1.5
    camera.azimuth, camera.elevation = 135, -20
    step = -1
    try:
        for step in range(count):
            target = initial_qpos.copy()
            if base_adr is None and data.time >= 1.0:
                # Same measured 0.25 rad arm motion in every variant.
                target[qindices[0]] += 0.25 * min(1.0, (float(data.time) - 1.0) / 0.5)
            data.ctrl[:] = initial_ctrl
            for actuator, joint, qadr, vadr, position in mappings:
                if position:
                    control = target[qadr]
                else:
                    gear = model.actuator_gear[actuator, 0] * model.actuator_gainprm[actuator, 0]
                    if abs(gear) < 1e-12:
                        raise ValueError("zero actuator gear/gain")
                    control = (
                        80.0 * gain_scale * (target[qadr] - data.qpos[qadr])
                        - 4.0 * data.qvel[vadr]
                    ) / gear
                if model.actuator_ctrllimited[actuator]:
                    control = np.clip(control, *model.actuator_ctrlrange[actuator])
                data.ctrl[actuator] = control
            data.xfrc_applied[:] = 0
            if base_body is not None and 2.0 <= data.time < 2.2:
                data.xfrc_applied[base_body, 0] = float(model.body_mass.sum()) * 9.81 * 0.1
            mujoco.mj_step(model, data)
            if not all(np.isfinite(arr).all() for arr in (data.qpos, data.qvel, data.ctrl)):
                finite = False
                break
            if base_adr is not None:
                min_ratio = min(min_ratio, float(data.qpos[base_adr + 2]) / height)
                quat = data.qpos[base_adr + 3:base_adr + 7]
                cosine = float(np.clip(1 - 2 * (quat[1]**2 + quat[2]**2), -1, 1))
                max_tilt = max(max_tilt, math.degrees(math.acos(cosine)))
            for _, joint, qadr, _, _ in mappings:
                if model.jnt_limited[joint]:
                    lo, hi = model.jnt_range[joint]
                    max_violation = max(max_violation, lo - data.qpos[qadr], data.qpos[qadr] - hi)
            max_contacts = max(max_contacts, int(data.ncon))
            if data.time >= 1.0:
                errors.append(float(np.mean((data.qpos[qindices] - target[qindices])**2)))
            if step % sample_every == 0 or step == count - 1:
                times.append(float(data.time))
                trace.append(data.qpos.copy())
                velocities.append(data.qvel.copy())
                controls.append(data.ctrl.copy())
            if renderer is not None and writer is not None and step % frame_every == 0:
                try:
                    render_data.qpos[:] = data.qpos
                    render_data.qvel[:] = data.qvel
                    render_data.time = data.time
                    mujoco.mj_forward(model, render_data)
                    renderer.update_scene(render_data, camera=camera)
                    image = Image.fromarray(renderer.render())
                    draw = ImageDraw.Draw(image)
                    text = f"{scene.parent.name} | {label} | t={data.time:.2f}s"
                    draw.text((12, 12), text, fill="white")
                    text = "SIMULATION - posture/servo probe, NOT a walking policy"
                    draw.text((12, 32), text, fill="white")
                    writer.append_data(np.asarray(image))
                    if step == 0 or step >= count - frame_every:
                        phase = "start" if step == 0 else "end"
                        image.save(out / f"{label}-{phase}.png")
                except Exception as exc:
                    render_error = f"{type(exc).__name__}: {exc}"
                    writer.close()
                    writer = None
    finally:
        if writer is not None:
            writer.close()
        if renderer is not None:
            renderer.close()
    warnings = [int(w.number) for w in data.warning]
    valid = finite and step == count - 1 and not any(warnings) and bool(errors)
    metrics = {
        "engine_valid": bool(valid), "simulated_seconds": float(data.time),
        "steps": step + 1, "warning_counts": warnings,
        "min_base_height_ratio": float(min_ratio), "max_base_tilt_deg": float(max_tilt),
        "joint_rmse_rad": math.sqrt(sum(errors) / len(errors)) if errors else 0.0,
        "max_joint_limit_violation_rad": float(max_violation), "max_contacts": max_contacts,
        "final_base_height_m": float(data.qpos[base_adr + 2]) if base_adr is not None else None,
    }
    trace_path = out / f"{label}.npz"
    np.savez_compressed(trace_path, t=times, qpos=trace, qvel=velocities, ctrl=controls)
    result = {
        "label": label, "proportional_gain_scale": gain_scale, "metrics": metrics,
        "posture_or_tracking_qualified": qualified(metrics), "render_error": render_error,
        "trace_sha256": digest(trace_path), "trace": trace_path.name,
        "model": {"nq": model.nq, "nv": model.nv, "actuators": model.nu,
                  "controlled_hinges": len(mappings), "mass_kg": float(model.body_mass.sum()),
                  "timestep_s": dt, "initial_keyframe": 0 if model.nkey else None},
    }
    payload = json.dumps(result, indent=2, allow_nan=False)
    (out / f"{label}.json").write_text(payload + "\n", encoding="utf-8")
    print(scene.parent.name, label, json.dumps(metrics, allow_nan=False), flush=True)
    return result, np.asarray(trace)


def main() -> int:
    import mujoco
    import numpy as np

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    source, output = args.models_root.resolve(strict=True), args.output.resolve()
    if output == source or source in output.parents:
        parser.error("output must not be inside the model snapshot")
    if output.exists():
        parser.error("output already exists; choose a fresh directory to preserve evidence")
    output.mkdir(parents=True)
    sha = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if sha != MENAGERIE_SHA:
        raise ValueError("model checkout does not match the pinned Menagerie revision")
    dirty = subprocess.check_output(
        ["git", "-C", str(source), "status", "--porcelain", "--", *MODELS], text=True
    )
    if dirty.strip():
        raise ValueError("model checkout has local modifications")
    summary = {
        "schema_version": 1, "kind": "robot_model_physics_probe",
        "not_a_robotci_navigation_gate": True, "menagerie_commit": sha,
        "python": platform.python_version(), "mujoco": mujoco.__version__,
        "numpy": np.__version__, "platform": platform.platform(),
        "harness_sha256": digest(Path(__file__)),
        "robotci_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "protocol": {"duration_s": DURATION, "baseline_repeats": 3, "candidate_repeats": 2,
                     "candidate_p_gain_scale": GAIN_SCALE, "fixed_damping": True,
                     "repeat_tolerance_abs": 1e-10, "holdout_validation": False},
        "models": [],
    }
    for name in MODELS:
        dest = output / name
        dest.mkdir()
        runs, traces = [], []
        try:
            before = manifest(source / name)
            if "LICENSE" not in before or "scene.xml" not in before:
                raise ValueError("model snapshot is missing its scene or license")
            (dest / "LICENSE").write_bytes((source / name / "LICENSE").read_bytes())
            for index in range(5):
                label = f"baseline-{index + 1}" if index < 3 else f"candidate-{index - 2}"
                result, trace = episode(
                    source / name / "scene.xml", dest, label,
                    1.0 if index < 3 else GAIN_SCALE, args.render and index in (0, 3),
                )
                runs.append(result)
                traces.append(trace)
            equal_shapes = all(item.shape == traces[0].shape for item in traces[1:3])
            delta = (
                max(float(np.max(np.abs(traces[0] - item))) for item in traces[1:3])
                if equal_shapes else None
            )
            candidate_delta = (
                float(np.max(np.abs(traces[3] - traces[4])))
                if traces[3].shape == traces[4].shape else None
            )
            if before != manifest(source / name):
                raise ValueError("source model files changed during the experiment")
            entry = {
                "name": name, "execution_complete": True, "source_files": before,
                "source_unchanged": True, "baseline_max_qpos_delta": delta,
                "candidate_max_qpos_delta": candidate_delta, "episodes": runs,
                "finding": compare(
                    runs[0]["metrics"], runs[3]["metrics"], delta is not None and delta <= 1e-10
                ),
            }
        except Exception as exc:
            entry = {"name": name, "execution_complete": False, "episodes": runs,
                     "error": f"{type(exc).__name__}: {exc}"}
        summary["models"].append(entry)
        payload = json.dumps(summary, indent=2, allow_nan=False)
        (output / "summary.json").write_text(payload + "\n", encoding="utf-8")
    return 0 if all(item["execution_complete"] for item in summary["models"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
