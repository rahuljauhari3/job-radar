import json

import pytest

from radar import cli


@pytest.fixture(autouse=True)
def ntfy_env(monkeypatch):
    for var in ("NTFY_SERVER", "NTFY_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NTFY_TOPIC", "my-topic")


def test_test_push_sends_to_topic(respx_mock, capsys):
    route = respx_mock.post("https://ntfy.sh").respond(200, json={"id": "x"})

    assert cli.main(["test-push"]) == 0
    assert json.loads(route.calls.last.request.content)["topic"] == "my-topic"
    assert capsys.readouterr().out.strip() == "sent to https://ntfy.sh"


def test_ntfy_server_variable_picks_the_server(respx_mock, monkeypatch, capsys):
    monkeypatch.setenv("NTFY_SERVER", "https://ntf-ai.app/")
    route = respx_mock.post("https://ntf-ai.app").respond(200, json={"id": "x"})

    assert cli.main(["test-push"]) == 0
    assert route.called
    assert capsys.readouterr().out.strip() == "sent to https://ntf-ai.app"


def test_unset_repo_variable_falls_back_to_ntfy_sh(respx_mock, monkeypatch):
    monkeypatch.setenv("NTFY_SERVER", "")  # what ${{ vars.NTFY_SERVER }} gives when the variable is unset
    route = respx_mock.post("https://ntfy.sh").respond(200, json={"id": "x"})

    assert cli.main(["test-push"]) == 0
    assert route.called


def test_test_push_reports_why_ntfy_refused(respx_mock, capsys):
    respx_mock.post("https://ntfy.sh").respond(400, json={"code": 40009, "error": "invalid topic"})

    assert cli.main(["test-push"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("failed: HTTP 400") and "invalid topic" in out
