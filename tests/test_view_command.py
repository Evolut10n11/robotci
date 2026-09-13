from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import robotci.entrypoint as entrypoint

runner = CliRunner()


def test_view_demo_starts_local_viewer(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_serve_viewer(replay: object, **kwargs: object) -> str:
        captured["replay"] = replay
        captured.update(kwargs)
        return "http://127.0.0.1:8765/"

    monkeypatch.setattr(entrypoint, "serve_viewer", fake_serve_viewer)

    result = runner.invoke(entrypoint.app, ["view", "--demo", "--no-open"])

    assert result.exit_code == 0
    assert "deterministic_demo" in result.stdout
    replay = captured["replay"]
    assert isinstance(replay, dict)
    assert replay["schema_version"] == 1
    assert captured["open_browser"] is False


def test_view_requires_replay_or_demo() -> None:
    result = runner.invoke(entrypoint.app, ["view"])

    assert result.exit_code == 3
    assert "pass --demo or --replay" in result.stdout


def test_view_rejects_demo_and_replay_together(tmp_path: Path) -> None:
    replay_path = tmp_path / "replay.json"
    replay_path.write_text("{}", encoding="utf-8")

    result = runner.invoke(
        entrypoint.app,
        ["view", "--demo", "--replay", str(replay_path)],
    )

    assert result.exit_code == 3
    assert "either --demo or --replay" in result.stdout


def test_view_reports_missing_replay_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"

    result = runner.invoke(entrypoint.app, ["view", "--replay", str(missing)])

    assert result.exit_code == 3
    assert "replay file does not exist" in result.stdout
