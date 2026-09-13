from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.request import urlopen

import pytest

from robotci.viewer import ViewerError, create_viewer_server, demo_replay, load_replay, validate_replay


def test_demo_replay_is_valid() -> None:
    replay = validate_replay(demo_replay())

    assert replay["schema_version"] == 1
    assert replay["status"] == "PASS"
    assert replay["runtime"] == "deterministic_demo"
    assert len(replay["samples"]) >= 2


def test_validate_replay_rejects_missing_samples() -> None:
    replay = demo_replay()
    replay["samples"] = []

    with pytest.raises(ViewerError, match="at least two samples"):
        validate_replay(replay)


def test_validate_replay_rejects_out_of_order_samples() -> None:
    replay = demo_replay()
    replay["samples"][1]["t"] = -1.0

    with pytest.raises(ViewerError, match="timestamps"):
        validate_replay(replay)


def test_load_replay_reads_valid_json(tmp_path: Path) -> None:
    path = tmp_path / "replay.json"
    path.write_text(json.dumps(demo_replay()), encoding="utf-8")

    replay = load_replay(path)

    assert replay["scenario"] == "deterministic_demo"


def test_load_replay_reports_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "replay.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ViewerError, match="not valid JSON"):
        load_replay(path)


def test_viewer_serves_replay_api_and_assets() -> None:
    server = create_viewer_server(demo_replay(), host="127.0.0.1", port=0)
    port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with urlopen(f"http://127.0.0.1:{port}/api/replay", timeout=2) as response:
            replay = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert replay["schema_version"] == 1
            assert replay["scenario"] == "deterministic_demo"

        with urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
            html = response.read().decode("utf-8")
            assert response.status == 200
            assert 'id="root"' in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
