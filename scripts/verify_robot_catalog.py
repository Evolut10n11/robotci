"""Compare imported reference frames with real MuJoCo forward kinematics."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> None:
    import mujoco
    import numpy as np

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = []
    for model_id, file in [
        ("unitree_go2", "go2.xml"),
        ("unitree_g1", "g1.xml"),
        ("franka_emika_panda", "panda.xml"),
    ]:
        manifest = json.loads((args.catalog / f"{model_id}.json").read_text())
        raw = (args.source / model_id / file).read_text()
        digest = hashlib.sha256(raw.replace("\r\n", "\n").strip().encode()).hexdigest()
        assert digest == manifest["source_sha256"], model_id
        model = mujoco.MjModel.from_xml_path(str(args.source / model_id / file))
        data = mujoco.MjData(model)
        for key in ["home", "stand"]:
            key_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, key)
            if key_id >= 0:
                mujoco.mj_resetDataKeyframe(model, data, key_id)
                break
        mujoco.mj_forward(model, data)
        errors = []
        for name, frame in manifest["reference_frames"].items():
            body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
            assert body_id >= 0, (model_id, name)
            position_error = float(np.max(np.abs(data.xpos[body_id] - frame["position"])))
            expected = np.roll(data.xquat[body_id], -1)
            observed = np.asarray(frame["quaternion_xyzw"])
            rotation_error = float(
                min(np.max(abs(expected - observed)), np.max(abs(expected + observed)))
            )
            assert position_error < 1e-6 and rotation_error < 1e-6, (
                model_id,
                name,
                position_error,
                rotation_error,
            )
            errors.append(max(position_error, rotation_error))
        results.append(
            {
                "model": model_id,
                "body_frames": len(errors),
                "max_error": max(errors),
                "status": "PASS",
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"mujoco": mujoco.__version__, "models": results}, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
