import json

import pytest

from radar import cli


@pytest.fixture(autouse=True)
def push_env(monkeypatch):
    for var in ("NTFY_SERVER", "NTFY_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NTFY_TOPIC", "my-topic")


def test_test_push_sends_to_topic_on_ntf_ai(respx_mock, capsys):
    route = respx_mock.post("https://ntf-ai.app").respond(200, json={"id": "x"})

    assert cli.main(["test-push"]) == 0
    assert json.loads(route.calls.last.request.content)["topic"] == "my-topic"
    assert capsys.readouterr().out.strip() == "sent to https://ntf-ai.app"


def test_empty_server_variable_still_uses_ntf_ai(respx_mock, monkeypatch):
    monkeypatch.setenv("NTFY_SERVER", "")
    route = respx_mock.post("https://ntf-ai.app").respond(200, json={"id": "x"})

    assert cli.main(["test-push"]) == 0
    assert route.called


def test_self_hosted_server_override(respx_mock, monkeypatch, capsys):
    monkeypatch.setenv("NTFY_SERVER", "https://push.example.com/")
    route = respx_mock.post("https://push.example.com").respond(200, json={"id": "x"})

    assert cli.main(["test-push"]) == 0
    assert route.called
    assert capsys.readouterr().out.strip() == "sent to https://push.example.com"


def test_test_push_reports_why_the_server_refused(respx_mock, capsys):
    respx_mock.post("https://ntf-ai.app").respond(400, json={"code": 40009, "error": "invalid topic"})

    assert cli.main(["test-push"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("failed: HTTP 400") and "invalid topic" in out
