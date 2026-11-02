"""Three polls against mocked sources: bootstrap, one new posting, nothing new."""

import asyncio
import json
import shutil
import time
from pathlib import Path

import httpx
import pytest
import yaml

from radar import pipeline
from radar.sources import levels

NOW = time.time()
LISTINGS = "https://raw.githubusercontent.com/Test/Repo/dev/.github/scripts/listings.json"


def listing(id_, title, company="Acme", posted=NOW - 3600):
    return {
        "id": id_, "title": title, "company_name": company, "url": f"https://acme.example/{id_}",
        "locations": ["Boston, MA"], "terms": ["Summer 2027"], "date_posted": posted, "active": True,
        "is_visible": True, "sponsorship": "Other", "degrees": ["Bachelor's", "Master's"], "category": "Software",
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    cfg = tmp_path / "config"
    cfg.mkdir()
    shutil.copy("config/profile.yaml", cfg / "profile.yaml")
    sources = yaml.safe_load(Path("config/sources.yaml").read_text())
    sources["simplify"]["repos"] = ["Test/Repo"]
    sources["levels"]["queries"] = ["software engineer"]
    sources["levels"]["max_pages"] = 1
    sources["ats"] = {"rotation": 1, "watchlist": {"greenhouse": {"acme": "Acme"}}}
    (cfg / "sources.yaml").write_text(yaml.safe_dump(sources))
    monkeypatch.setenv("NTFY_TOPIC", "test-topic")
    monkeypatch.setattr(levels, "CALL_GAP_SECONDS", 0)
    return pipeline.Options(config_dir=cfg, state_path=tmp_path / "state.json", feed_path=tmp_path / "feed.json")


class Fake:
    """Mutable source data plus a record of every push sent."""

    def __init__(self, respx_mock):
        self.rows = [listing("L1", "Machine Learning Engineer Intern")]
        self.greenhouse = []
        self.levels_jobs = []
        self.pushes = []
        self.etag = 0
        respx_mock.get(LISTINGS).mock(side_effect=self._listings)
        respx_mock.get("https://api.github.com/repos/Test/Repo/issues").respond(json=[])
        respx_mock.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs").mock(
            side_effect=lambda r: httpx.Response(200, json={"jobs": self.greenhouse})
        )
        respx_mock.get(url__regex=r"https://boards-api\.greenhouse\.io/v1/boards/acme/jobs/\d+").respond(
            json={"content": "&lt;p&gt;Work on vLLM and PyTorch inference in C++.&lt;/p&gt;"}
        )
        respx_mock.post("https://mcp.levels.fyi/").mock(side_effect=self._mcp)
        respx_mock.post("https://ntfy.sh").mock(side_effect=self._ntfy)
        respx_mock.get(url__startswith="https://acme.example/").respond(200, text="")

    def _listings(self, request):
        tag = f'"v{self.etag}"'
        if request.headers.get("If-None-Match") == tag:
            return httpx.Response(304)
        return httpx.Response(200, json=self.rows, headers={"ETag": tag})

    def _mcp(self, request):
        body = json.loads(request.content)
        if body["method"] == "initialize":
            result = {"protocolVersion": "2025-06-18"}
        elif body["params"]["name"] == "search-jobs":
            result = {"content": [{"type": "text", "text": json.dumps({"jobs": self.levels_jobs})}]}
        else:
            result = {"content": [{"type": "text", "text": json.dumps({"description": "Python backend services."})}]}
        sse = f"event: message\ndata: {json.dumps({'jsonrpc': '2.0', 'id': body['id'], 'result': result})}\n\n"
        return httpx.Response(200, text=sse, headers={"Content-Type": "text/event-stream"})

    def _ntfy(self, request):
        self.pushes.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "x"})


def test_bootstrap_then_new_posting_then_quiet(env, respx_mock):
    fake = Fake(respx_mock)

    stats = asyncio.run(pipeline.run(env, now=NOW))
    assert stats["bootstrap"] and not stats["errors"]
    assert [p["title"] for p in fake.pushes] == ["Job Radar is live"]
    feed = json.loads(env.feed_path.read_text())
    assert [j["title"] for j in feed["jobs"]] == ["Machine Learning Engineer Intern"]

    # A new posting appears on Simplify and, reworded, on the employer's board; plus one on levels.fyi.
    fake.pushes.clear()
    fake.etag += 1
    fake.rows.append(listing("L2", "Software Engineer Intern - Inference"))
    fake.greenhouse = [{
        "id": 77, "title": "2027 Summer Intern, Software Engineer - Inference", "company_name": "Acme",
        "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/77", "location": {"name": "Boston, MA"},
        "first_published": "2026-11-02T10:00:00Z",
    }]
    fake.levels_jobs = [{
        "jobId": "lv1", "title": "Backend Software Engineer Intern", "company": "Globex",
        "locations": ["Seattle, WA"], "postedAt": "2026-11-02T09:00:00Z",
        "url": "https://www.levels.fyi/jobs?jobId=lv1", "applyUrl": "https://globex.example/apply",
    }]
    stats = asyncio.run(pipeline.run(env, now=NOW + 600))
    assert not stats["bootstrap"] and not stats["errors"]
    titles = sorted(p["title"] for p in fake.pushes)
    assert titles == ["Acme — Software Engineer Intern - Inference", "Globex — Backend Software Engineer Intern"]
    acme = next(p for p in fake.pushes if p["title"].startswith("Acme"))
    assert acme["click"] == "https://acme.example/L2"
    assert "Simplify" in acme["message"] and "Greenhouse" in acme["message"]
    assert acme["actions"][1]["url"].startswith("jobradar://job/")
    feed = json.loads(env.feed_path.read_text())
    assert len(feed["jobs"]) == 3
    inference = next(j for j in feed["jobs"] if "Inference" in j["title"])
    assert inference["tier"] == "A" and {s["kind"] for s in inference["sources"]} == {"simplify", "greenhouse"}

    # Nothing changed: no pushes, Simplify answers 304.
    fake.pushes.clear()
    stats = asyncio.run(pipeline.run(env, now=NOW + 1200))
    assert stats["sources"]["simplify"] == "unchanged"
    assert stats["new"] == 0 and fake.pushes == []


def test_dry_run_writes_nothing(env, respx_mock):
    fake = Fake(respx_mock)
    env.dry_run = True
    asyncio.run(pipeline.run(env, now=NOW))
    assert fake.pushes == [] and not env.state_path.exists() and not env.feed_path.exists()
