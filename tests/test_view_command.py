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


def test_view_replay_pair_is_visual_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    from robotci.viewer import demo_replay

    replay = tmp_path / "candidate.replay.json"
    replay.write_text(json.dumps(demo_replay()))
    captured = {}
    monkeypatch.setattr(entrypoint, "serve_viewer", lambda *args, **kwargs: captured.update(kwargs))
    result = runner.invoke(
        entrypoint.app, ["view", "--replay", str(replay), "--baseline", str(replay), "--no-open"]
    )
    assert result.exit_code == 0
    assert captured["session"]["gate"] is None
    assert captured["session"]["scenarios"][0]["baseline"]["replay"]


def test_view_suite_evaluates_gate_without_requiring_replays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixtures = Path(__file__).parent / "fixtures" / "gate-suite"
    captured = {}
    monkeypatch.setattr(entrypoint, "serve_viewer", lambda *args, **kwargs: captured.update(kwargs))
    result = runner.invoke(
        entrypoint.app,
        [
            "view",
            "--suite",
            str(fixtures / "regression" / "suite-result.json"),
            "--baseline-suite",
            str(fixtures / "baseline" / "suite-result.json"),
            "--scenario",
            "route",
            "--no-open",
        ],
    )
    assert result.exit_code == 0
    assert captured["session"]["gate"]["status"] == "REGRESSION"
    assert captured["session"]["scenarios"][0]["candidate"]["replay"] is None


@pytest.mark.parametrize(
    "arguments",
    [
        ["--demo", "--baseline", "anything.json"],
        ["--demo", "--baseline-suite", "anything.json"],
        ["--demo", "--scenario", "anything"],
        ["--demo", "--suite", "anything.json"],
    ],
)
def test_view_rejects_flags_for_a_different_source(arguments: list[str]) -> None:
    result = runner.invoke(entrypoint.app, ["view", *arguments])
    assert result.exit_code == 3


@pytest.mark.parametrize("custom_store", [False, True])
def test_view_resolves_saved_baseline_and_uses_existing_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, custom_store: bool,
) -> None:
    from robotci.baselines import capture_baseline

    fixtures = Path(__file__).parent / "fixtures" / "gate-suite"
    store = tmp_path / ("saved runs" if custom_store else ".robotci/baselines")
    capture_baseline("main-nav", fixtures / "baseline/suite-result.json", store_root=store)
    monkeypatch.chdir(tmp_path)
    captured = {}
    monkeypatch.setattr(entrypoint, "serve_viewer", lambda *args, **kw: captured.update(kw))
    arguments = [
        "view", "--suite", str(fixtures / "regression/suite-result.json"),
        "--baseline-name", "main-nav", "--no-open",
    ]
    if custom_store:
        arguments.extend(["--baseline-store", str(store)])
    result = runner.invoke(entrypoint.app, arguments)
    assert result.exit_code == 0, result.stdout
    assert captured["session"]["gate"]["status"] == "REGRESSION"
    assert captured["session"]["baseline_label"] == "main-nav"
    assert len(captured["session"]["scenarios"][0]["comparison"]["findings"]) == 5


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--demo", "--baseline-name", "main-nav"], "require --suite"),
        (["--demo", "--baseline-store", ".robotci/baselines"], "requires --baseline-name"),
        (["--suite", "unused.json", "--baseline-name", "main-nav",
          "--baseline-suite", "unused.json"], "not both"),
        (["--suite", "unused.json", "--baseline-name", "../escape"], "baseline name"),
        (["--suite", "unused.json", "--baseline-name", "missing"], "does not exist"),
    ],
)
def test_view_rejects_invalid_saved_baseline_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, arguments: list[str], message: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(entrypoint.app, ["view", *arguments])
    assert result.exit_code == 3
    assert message in " ".join(result.stdout.split())


def test_view_prints_actual_bound_port(monkeypatch: pytest.MonkeyPatch) -> None:
    def serve(*args, **kwargs):
        assert kwargs["port"] == 0
        kwargs["on_ready"]("http://127.0.0.1:49152/")

    monkeypatch.setattr(entrypoint, "serve_viewer", serve)
    result = runner.invoke(entrypoint.app, ["view", "--demo", "--port", "0", "--no-open"])
    assert result.exit_code == 0
    assert "http://127.0.0.1:49152/" in result.stdout
    assert "http://127.0.0.1:0/" not in result.stdout
