"""levels.fyi job board through its official, free MCP server (streamable HTTP)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

import httpx

from radar.http import request
from radar.models import Job

MCP_URL = "https://mcp.levels.fyi/"
# The free tier allows ~20 calls a minute, shared per network.
CALL_GAP_SECONDS = 3.2


class LevelsMCP:
    def __init__(self, c: httpx.AsyncClient):
        self.c = c
        self.session: str | None = None
        self._id = 0

    async def _rpc(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        body = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}
        r = await request(self.c, "POST", MCP_URL, json=body, headers=headers)
        r.raise_for_status()
        self.session = r.headers.get("Mcp-Session-Id", self.session)
        return _parse_rpc(r.text)

    async def initialize(self):
        await self._rpc(
            "initialize",
            {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "job-radar", "version": "0.1"}},
        )

    async def call(self, tool: str, args: dict) -> dict:
        res = await self._rpc("tools/call", {"name": tool, "arguments": args})
        result = res.get("result", {})
        text = "".join(p.get("text", "") for p in result.get("content", []))
        if result.get("isError"):
            raise RuntimeError(f"levels {tool}: {text[:200]}")
        await asyncio.sleep(CALL_GAP_SECONDS)
        return json.loads(text)


def _parse_rpc(text: str) -> dict:
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)
    for line in text.splitlines():  # server-sent events
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    raise ValueError(f"unexpected MCP response: {text[:200]}")


def parse_job(j: dict) -> Job:
    posted = j.get("postedAt")
    return Job(
        source="levels",
        source_id=j["jobId"],
        company=j.get("company", ""),
        title=j.get("title", ""),
        url=j.get("applyUrl") or j.get("url", ""),
        locations=j.get("locations") or [],
        posted_at=datetime.fromisoformat(posted.replace("Z", "+00:00")).timestamp() if posted else None,
    )


async def fetch(c: httpx.AsyncClient, cfg: dict, bootstrap: bool) -> list[Job]:
    mcp = LevelsMCP(c)
    await mcp.initialize()
    jobs: dict[str, Job] = {}
    for q in cfg["queries"]:
        offset = None
        for _ in range(cfg.get("max_pages", 1)):
            args = {
                "query": q,
                "locationSlug": cfg["location_slug"],
                "standardLevels": ["internship"],
                "postedWithinDays": 14 if bootstrap else cfg["posted_within_days"],
                "sortBy": "date_published",
                "limit": 25,
            }
            if offset:
                args["offset"] = offset
            page = await mcp.call("search-jobs", args)
            for j in page.get("jobs", []):
                jobs.setdefault(j["jobId"], parse_job(j))
            offset = page.get("nextOffset")
            if not offset:
                break
    return list(jobs.values())


async def describe(c: httpx.AsyncClient, job_ids: list[str]) -> dict[str, str]:
    if not job_ids:
        return {}
    mcp = LevelsMCP(c)
    await mcp.initialize()
    out = {}
    for jid in job_ids:
        try:
            d = await mcp.call("get-job", {"jobId": jid})
        except Exception:
            continue
        out[jid] = d.get("description") or d.get("job", {}).get("description", "")
    return out
