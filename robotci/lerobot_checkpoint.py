"""Explicit, hash-verified download of the supported public PushT checkpoint."""

from __future__ import annotations

import copy
import hashlib
import http.client
import json
import os
import shutil
import stat
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MANIFEST_NAME = "robotci-checkpoint.json"
PINNED_CHECKPOINT = {
    "schema_version": 1,
    "source": {
        "repo_id": "lerobot/diffusion_pusht",
        "revision": "84a7c23178445c6bbf7e1a884ff497017910f653",
    },
    "files": {
        "config.json": {
            "size_bytes": 1509,
            "sha256": "d391a7bf488accd1c26b2043482f0060b0855b1ec236f3d7358486918472c0a5",
        },
        "model.safetensors": {
            "size_bytes": 1050862408,
            "sha256": "995d14d35db57d95c35ad9704c3d79c8612b7bc45f3877e5c46c2cdc516856a8",
        },
    },
}
_CHUNK_BYTES = 1024 * 1024


class LeRobotCheckpointError(ValueError):
    """The requested checkpoint is unavailable, incomplete or altered."""


class _HTTPSRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise LeRobotCheckpointError("Checkpoint download redirected outside HTTPS")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _regular_file(path: Path, expected_size: int) -> None:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size != expected_size:
            raise LeRobotCheckpointError(f"Unexpected file type or size: {path.name}")
    except OSError as exc:
        raise LeRobotCheckpointError(f"Cannot read checkpoint file: {path.name}") from exc


def load_checkpoint_manifest(checkpoint: Path) -> dict:
    """Read the fixed source declaration without loading model weights."""
    manifest_path = checkpoint / MANIFEST_NAME
    try:
        info = manifest_path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 8192:
            raise LeRobotCheckpointError("Invalid checkpoint manifest file")
        with manifest_path.open("rb") as source:
            raw = source.read(8193)
        if len(raw) > 8192:
            raise LeRobotCheckpointError("Checkpoint manifest exceeds its size limit")
        manifest = json.loads(raw)
    except (OSError, ValueError, UnicodeError) as exc:
        raise LeRobotCheckpointError(
            "Missing or invalid robotci-checkpoint.json; use robotci lerobot fetch"
        ) from exc
    if manifest != PINNED_CHECKPOINT:
        raise LeRobotCheckpointError("Checkpoint manifest does not match the supported source")
    return copy.deepcopy(PINNED_CHECKPOINT)


def verify_checkpoint(checkpoint: Path) -> dict:
    """Verify exact pinned bytes before any optional ML library reads the files."""
    manifest = load_checkpoint_manifest(checkpoint)
    for name, expected in manifest["files"].items():
        path = checkpoint / name
        _regular_file(path, expected["size_bytes"])
        digest = hashlib.sha256()
        count = 0
        try:
            with path.open("rb") as source:
                while chunk := source.read(_CHUNK_BYTES):
                    count += len(chunk)
                    if count > expected["size_bytes"]:
                        raise LeRobotCheckpointError(f"Checkpoint file grew while reading: {name}")
                    digest.update(chunk)
        except OSError as exc:
            raise LeRobotCheckpointError(f"Cannot read checkpoint file: {name}") from exc
        if count != expected["size_bytes"] or digest.hexdigest() != expected["sha256"]:
            raise LeRobotCheckpointError(f"Checkpoint SHA-256 mismatch: {name}")
    return manifest


def _download_file(url: str, path: Path, expected: dict) -> None:
    opener = urllib.request.build_opener(_HTTPSRedirectHandler())
    request = urllib.request.Request(url, headers={"User-Agent": "RobotCI/0.1.0a1"})
    digest = hashlib.sha256()
    count = 0
    deadline = time.monotonic() + 900
    with opener.open(request, timeout=30) as response, path.open("xb") as target:
        while chunk := response.read1(_CHUNK_BYTES):
            count += len(chunk)
            if count > expected["size_bytes"]:
                raise LeRobotCheckpointError(f"Download exceeds pinned size: {path.name}")
            if time.monotonic() > deadline:
                raise LeRobotCheckpointError(f"Download exceeded 15 minutes: {path.name}")
            digest.update(chunk)
            target.write(chunk)
    if count != expected["size_bytes"] or digest.hexdigest() != expected["sha256"]:
        raise LeRobotCheckpointError(f"Downloaded file does not match pinned SHA-256: {path.name}")


def fetch_checkpoint(destination: Path) -> dict:
    """Download once; an existing destination is checked and never overwritten."""
    destination = destination.expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        return verify_checkpoint(destination)
    stage: Path | None = None
    claimed = False
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Reserve the name exclusively, preventing competing fetches from replacing it.
        destination.mkdir()
        claimed = True
        stage = Path(tempfile.mkdtemp(prefix=".robotci-checkpoint-", dir=destination.parent))
        source = PINNED_CHECKPOINT["source"]
        base = f"https://huggingface.co/{source['repo_id']}/resolve/{source['revision']}"
        for name, expected in PINNED_CHECKPOINT["files"].items():
            _download_file(f"{base}/{name}", stage / name, expected)
        (stage / MANIFEST_NAME).write_text(
            json.dumps(PINNED_CHECKPOINT, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        # Publish the manifest last; interrupted downloads never look complete.
        for name in (*PINNED_CHECKPOINT["files"], MANIFEST_NAME):
            os.link(stage / name, destination / name)
        return copy.deepcopy(PINNED_CHECKPOINT)
    except (OSError, urllib.error.URLError, http.client.HTTPException) as exc:
        raise LeRobotCheckpointError(f"Cannot download the pinned PushT checkpoint: {exc}") from exc
    finally:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)
        if claimed and not (destination / MANIFEST_NAME).exists():
            # Remove only an empty reservation, never existing or partially published evidence.
            try:
                destination.rmdir()
            except OSError:
                pass
