from __future__ import annotations

import copy
import hashlib
import http.client
import json
from pathlib import Path

import pytest

from robotci import lerobot_checkpoint as checkpoint


@pytest.fixture
def tiny_source(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    files = {"config.json": b'{"type":"diffusion"}', "model.safetensors": b"bounded-test-weight"}
    manifest = copy.deepcopy(checkpoint.PINNED_CHECKPOINT)
    for name, raw in files.items():
        manifest["files"][name] = {
            "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()
        }
    monkeypatch.setattr(checkpoint, "PINNED_CHECKPOINT", manifest)
    return files


def _fake_download(files: dict[str, bytes]):
    def download(url: str, path: Path, expected: dict) -> None:
        assert url.startswith("https://huggingface.co/lerobot/diffusion_pusht/resolve/")
        assert checkpoint.PINNED_CHECKPOINT["source"]["revision"] in url
        assert expected["size_bytes"] == len(files[path.name])
        path.write_bytes(files[path.name])
    return download


def test_fetch_publishes_verified_manifest_and_existing_fetch_is_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tiny_source: dict[str, bytes]
) -> None:
    monkeypatch.setattr(checkpoint, "_download_file", _fake_download(tiny_source))
    destination = tmp_path / "models" / "pusht"
    result = checkpoint.fetch_checkpoint(destination)
    assert result == checkpoint.PINNED_CHECKPOINT
    assert checkpoint.verify_checkpoint(destination) == result
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in destination.iterdir()}

    def no_network(*args):
        raise AssertionError("An existing checkpoint must be verified offline")

    monkeypatch.setattr(checkpoint, "_download_file", no_network)
    assert checkpoint.fetch_checkpoint(destination) == result
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in destination.iterdir()} == before
    assert list(destination.parent.glob(".robotci-checkpoint-*")) == []


def test_altered_existing_weights_are_rejected_without_repair_or_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tiny_source: dict[str, bytes]
) -> None:
    monkeypatch.setattr(checkpoint, "_download_file", _fake_download(tiny_source))
    destination = tmp_path / "pusht"
    checkpoint.fetch_checkpoint(destination)
    weights = destination / "model.safetensors"
    altered = b"x" * weights.stat().st_size
    weights.write_bytes(altered)
    with pytest.raises(checkpoint.LeRobotCheckpointError, match="SHA-256"):
        checkpoint.fetch_checkpoint(destination)
    assert weights.read_bytes() == altered


def test_file_created_during_download_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tiny_source: dict[str, bytes]
) -> None:
    destination = tmp_path / "pusht"
    original_download = _fake_download(tiny_source)

    def concurrent_file(url: str, path: Path, expected: dict) -> None:
        original_download(url, path, expected)
        if path.name == "config.json":
            (destination / "config.json").write_bytes(b"other process")

    monkeypatch.setattr(checkpoint, "_download_file", concurrent_file)
    with pytest.raises(checkpoint.LeRobotCheckpointError):
        checkpoint.fetch_checkpoint(destination)
    assert (destination / "config.json").read_bytes() == b"other process"
    assert not (destination / checkpoint.MANIFEST_NAME).exists()


def test_failed_download_never_publishes_a_complete_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tiny_source: dict[str, bytes]
) -> None:
    def interrupted(url: str, path: Path, expected: dict) -> None:
        path.write_bytes(b"partial")
        raise OSError("connection interrupted")

    monkeypatch.setattr(checkpoint, "_download_file", interrupted)
    destination = tmp_path / "pusht"
    with pytest.raises(checkpoint.LeRobotCheckpointError, match="connection interrupted"):
        checkpoint.fetch_checkpoint(destination)
    assert not destination.exists()
    assert list(tmp_path.iterdir()) == []


def test_interrupted_http_body_is_a_typed_download_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupted(*args):
        raise http.client.IncompleteRead(b"partial", 12)

    monkeypatch.setattr(checkpoint, "_download_file", interrupted)
    with pytest.raises(checkpoint.LeRobotCheckpointError, match="IncompleteRead"):
        checkpoint.fetch_checkpoint(tmp_path / "pusht")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("kind", ["missing", "wrong-revision", "truncated", "directory"])
def test_incomplete_existing_destination_is_never_replaced(
    tmp_path: Path, tiny_source: dict[str, bytes], kind: str
) -> None:
    destination = tmp_path / "pusht"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("preserve", encoding="utf-8")
    manifest_path = destination / checkpoint.MANIFEST_NAME
    if kind == "wrong-revision":
        manifest = copy.deepcopy(checkpoint.PINNED_CHECKPOINT)
        manifest["source"]["revision"] = "0" * 40
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    elif kind == "truncated":
        manifest_path.write_bytes(b'{"schema_version":')
    elif kind == "directory":
        manifest_path.mkdir()
    with pytest.raises(checkpoint.LeRobotCheckpointError):
        checkpoint.fetch_checkpoint(destination)
    assert marker.read_text(encoding="utf-8") == "preserve"


@pytest.mark.parametrize(
    "payload", [b"too-long", b"no", b"bad!"], ids=["oversize", "short", "hash"]
)
def test_download_checks_size_and_hash_before_accepting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    import io

    class FakeOpener:
        def open(self, request, timeout):
            assert timeout == 30
            return io.BytesIO(payload)

    monkeypatch.setattr(checkpoint.urllib.request, "build_opener", lambda *args: FakeOpener())
    expected = {"size_bytes": 4, "sha256": hashlib.sha256(b"good").hexdigest()}
    with pytest.raises(checkpoint.LeRobotCheckpointError):
        checkpoint._download_file("https://huggingface.co/fixed", tmp_path / "weights", expected)


def test_https_redirect_does_not_downgrade_transport() -> None:
    handler = checkpoint._HTTPSRedirectHandler()
    with pytest.raises(checkpoint.LeRobotCheckpointError, match="HTTPS"):
        handler.redirect_request(None, None, 302, "redirect", {}, "http://example.com/model")
