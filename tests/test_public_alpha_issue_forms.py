from __future__ import annotations

from pathlib import Path

import yaml


def _load_issue_form(name: str) -> dict[str, object]:
    path = Path(__file__).parents[1] / ".github" / "ISSUE_TEMPLATE" / name
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_public_alpha_bug_report_form_is_valid_yaml() -> None:
    form = _load_issue_form("bug_report.yml")

    assert form["name"] == "Bug report"
    assert form["title"] == "[bug] "
    body = form["body"]
    assert isinstance(body, list)
    assert any(item.get("id") == "version" for item in body)
    assert any(item.get("id") == "reproduce" for item in body)
    assert any(item.get("id") == "safety" for item in body)


def test_public_alpha_pilot_feedback_form_is_valid_yaml() -> None:
    form = _load_issue_form("public_alpha_feedback.yml")

    assert form["name"] == "Public alpha pilot feedback"
    assert form["title"] == "[pilot] "
    body = form["body"]
    assert isinstance(body, list)
    assert any(item.get("id") == "completed" for item in body)
    assert any(item.get("id") == "reuse" for item in body)
    assert any(item.get("id") == "payment_signal" for item in body)
