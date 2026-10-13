"""Build reference metadata from a pinned local Menagerie checkout; no downloads."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from robotci.model_import import inspect_description

REVISION = "0059d4335f8156206f63a35662313385f7ad6d74"
EXPECTED_TREE_SHA256 = {
    "unitree_go2": "816e87b927c2dcf8da25a3886ae73bd025f6a0da8bcbff2de64e592c4820fc62",
    "unitree_g1": "47aa256de1a3a56c2d86967471cf47f5e4aabd6559adbb3b8536c213c368d3f3",
    "franka_emika_panda": "8dd045f59c9e770bc78d5908f9b32bf75f168ad8778ed2f86cfd7184f76b3607",
}
MODELS = {"unitree_go2": "go2.xml", "unitree_g1": "g1.xml", "franka_emika_panda": "panda.xml"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for model_id, filename in MODELS.items():
        source = args.source / model_id
        digest = hashlib.sha256()
        for file in sorted(p for p in source.rglob("*") if p.is_file()):
            digest.update(file.relative_to(source).as_posix().encode() + b"\0")
            digest.update(hashlib.sha256(file.read_bytes()).digest())
        if digest.hexdigest() != EXPECTED_TREE_SHA256[model_id]:
            raise ValueError("Model source differs from the pinned upstream directory")
        model = inspect_description((source / filename).read_text(encoding="utf-8"))
        model["model_id"] = model_id
        model["identification"] = "declared_catalog"
        model["catalog_asset"] = f"{model_id}.glb.gz"
        model["provenance"] = {
            "repository": "google-deepmind/mujoco_menagerie",
            "revision": REVISION,
            "file": f"{model_id}/{filename}",
            "pose": "upstream home/stand",
            "source_tree_sha256": EXPECTED_TREE_SHA256[model_id],
        }
        (args.output / f"{model_id}.json").write_text(
            json.dumps(model, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        shutil.copyfile(source / "LICENSE", args.output / f"{model_id}.LICENSE")


if __name__ == "__main__":
    main()
