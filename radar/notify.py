"""Phone push through ntfy (https://ntfy.sh): free, instant, no Apple developer account."""

from __future__ import annotations

import os

import httpx

from radar.http import request

TIER_TAGS = {"A": ["fire"], "B": ["briefcase"], "C": ["mag"]}
TIER_PRIORITY = {"A": 4, "B": 3, "C": 2}
APP_SCHEME = "jobradar://"


def job_message(item: dict) -> dict:
    where = ", ".join(item["locations"][:2]) or "Location n/a"
    when = ", ".join(item["terms"][:2])
    lines = [" · ".join(filter(None, [where, when, f"score {item['score']}"]))]
    if item["reasons"]:
        lines.append("Why: " + "; ".join(item["reasons"][:2]))
    if item["flags"]:
        lines.append("⚠️ " + ", ".join(item["flags"]))
    srcs = ", ".join(s["name"] for s in item["sources"])
    lines.append(f"via {srcs}")
    return {
        "title": f"{item['company']} — {item['title']}"[:250],
        "message": "\n".join(lines),
        "click": item["url"],
        "tags": TIER_TAGS.get(item["tier"], []),
        "priority": TIER_PRIORITY.get(item["tier"], 3),
        "actions": [
            {"action": "view", "label": "Apply", "url": item["url"]},
            {"action": "view", "label": "Open in Job Radar", "url": f"{APP_SCHEME}job/{item['id']}"},
        ],
    }


def summary_message(items: list[dict]) -> dict:
    lines = [f"• {i['company']} — {i['title']} ({i['tier']}{i['score']})" for i in items[:12]]
    if len(items) > 12:
        lines.append(f"…and {len(items) - 12} more")
    return {
        "title": f"{len(items)} more new internship matches",
        "message": "\n".join(lines),
        "click": f"{APP_SCHEME}feed",
        "tags": ["mag"],
        "priority": 2,
    }


class Notifier:
    def __init__(self, c: httpx.AsyncClient, topic: str | None = None, server: str | None = None):
        self.c = c
        self.topic = topic or os.environ.get("NTFY_TOPIC")
        self.server = (server or os.environ.get("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
        self.token = os.environ.get("NTFY_TOKEN")
        self.sent = 0

    @property
    def enabled(self) -> bool:
        return bool(self.topic)

    async def send(self, msg: dict) -> bool:
        if not self.enabled:
            return False
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        r = await request(self.c, "POST", self.server, json={"topic": self.topic, **msg}, headers=headers)
        if r.is_success:
            self.sent += 1
        return r.is_success
