"""One poll: fetch every source, merge duplicates, match, push, publish the feed."""

from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from radar import http
from radar.match import Profile, evaluate
from radar.models import Job
from radar.notify import Notifier, job_message, summary_message
from radar.sources import ats, levels, simplify
from radar.store import State, write_feed

# Which record supplies the fields when one posting shows up in several sources.
SOURCE_RANK = {"simplify": 0, "greenhouse": 1, "lever": 1, "ashby": 1, "smartrecruiters": 1, "simplify-pending": 2, "levels": 3}
SOURCE_LABEL = {
    "simplify": "Simplify",
    "simplify-pending": "Simplify (pending)",
    "levels": "levels.fyi",
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
    "smartrecruiters": "SmartRecruiters",
}


@dataclass
class Options:
    config_dir: Path = Path("config")
    state_path: Path = Path("data/state.json")
    feed_path: Path = Path("data/feed.json")
    dry_run: bool = False
    bootstrap: bool = False
    only: set[str] = field(default_factory=lambda: {"simplify", "levels", "ats"})
    github_token: str | None = None


def merge(jobs: list[Job]) -> tuple[Job, list[dict]]:
    """Combine one posting's records; returns the primary record and its source links."""
    jobs = sorted(jobs, key=lambda j: SOURCE_RANK.get(j.source, 9))
    primary = jobs[0]
    for other in jobs[1:]:
        primary.terms = list(dict.fromkeys(primary.terms + other.terms))
        primary.locations = list(dict.fromkeys(primary.locations + other.locations))[:12]
        if len(other.description) > len(primary.description):
            primary.description = other.description
        primary.sponsorship = primary.sponsorship or other.sponsorship
        primary.degrees = primary.degrees or other.degrees
        if other.posted_at and (not primary.posted_at or other.posted_at < primary.posted_at):
            primary.posted_at = other.posted_at
    sources, seen = [], set()
    for j in jobs:
        if j.source not in seen:
            seen.add(j.source)
            sources.append({"name": SOURCE_LABEL.get(j.source, j.source), "url": j.url, "kind": j.source, "id": j.source_id})
    return primary, sources


async def _gather_sources(c, opt: Options, cfg: dict, state: State, stats: dict, bootstrap: bool) -> list[Job]:
    jobs: list[Job] = []
    rows = None

    async def simplify_listings():
        nonlocal rows
        for repo in cfg["simplify"]["repos"]:
            data, etag = await simplify.fetch_listings(c, repo, cfg["simplify"]["branch"], state.etags.get(repo))
            if data is None:
                stats["sources"]["simplify"] = "unchanged"
                continue
            state.etags[repo] = etag
            rows = (rows or []) + data
            parsed = [j for j in map(simplify.parse_listing, data) if j]
            jobs.extend(parsed)
            stats["sources"]["simplify"] = len(parsed)

    async def simplify_pending():
        out = []
        for repo in cfg["simplify"]["repos"]:
            out += await simplify.fetch_pending(c, repo, cfg["simplify"]["pending_issue_label"], opt.github_token)
        jobs.extend(out)
        stats["sources"]["simplify-pending"] = len(out)

    async def levels_jobs():
        out = await levels.fetch(c, cfg["levels"], bootstrap)
        jobs.extend(out)
        stats["sources"]["levels"] = len(out)

    async def ats_jobs():
        if rows is not None:
            state.boards = ats.discover_boards(rows, cfg["ats"].get("watchlist"))
        elif not state.boards:
            state.boards = ats.discover_boards([], cfg["ats"].get("watchlist"))
        rotation = 1 if bootstrap else cfg["ats"]["rotation"]
        batch = ats.rotation_slice(state.boards, state.run, rotation)
        out, errors = await ats.fetch_boards(c, batch)
        jobs.extend(out)
        stats["sources"]["ats"] = {"boards": len(batch), "jobs": len(out), "errors": errors}

    # Simplify first: its listings are where the ATS boards are discovered.
    stages = [
        {"simplify": simplify_listings, "simplify-pending": simplify_pending},
        {"levels": levels_jobs, "ats": ats_jobs},
    ]
    enabled = {"simplify": "simplify", "simplify-pending": "simplify", "levels": "levels", "ats": "ats"}
    for stage in stages:
        names = [n for n in stage if enabled[n] in opt.only]
        results = await asyncio.gather(*(stage[n]() for n in names), return_exceptions=True)
        for name, res in zip(names, results):
            if isinstance(res, Exception):
                stats["errors"][name] = f"{type(res).__name__}: {res}"[:300]
    return jobs


async def _enrich(c, candidates: list[Job], limit: int) -> int:
    """Fetch job descriptions for new matches that lack one. Returns how many were filled."""
    todo = [j for j in candidates if not j.description][:limit]
    by_levels = [j for j in todo if j.source == "levels"][:15]
    others = [j for j in todo if j.source != "levels"]
    ashby_cache: dict = {}
    sem = asyncio.Semaphore(8)

    async def one(job: Job):
        async with sem:
            try:
                job.description = await ats.describe(c, job.url, ashby_cache)
            except Exception:
                pass

    await asyncio.gather(*(one(j) for j in others))
    if by_levels:
        try:
            got = await levels.describe(c, [j.source_id for j in by_levels])
        except Exception:
            got = {}
        for j in by_levels:
            j.description = got.get(j.source_id, "")
    return sum(1 for j in todo if j.description)


async def run(opt: Options, now: float | None = None) -> dict:
    t0 = time.time()
    now = now or t0
    profile = Profile.load(opt.config_dir / "profile.yaml")
    cfg = yaml.safe_load((opt.config_dir / "sources.yaml").read_text())
    limits = cfg["limits"]
    state = State.load(opt.state_path)
    bootstrap = opt.bootstrap or state.is_new
    stats: dict = {"sources": {}, "errors": {}, "bootstrap": bootstrap}

    async with http.client() as c:
        jobs = await _gather_sources(c, opt, cfg, state, stats, bootstrap)

        groups: dict[str, list[Job]] = defaultdict(list)
        for j in jobs:
            groups[j.key].append(j)

        new: list[tuple[Job, list[dict]]] = []
        matched = 0
        for key, group in groups.items():
            primary, sources = merge(group)
            if key in state.feed:
                item = state.feed[key]
                known = {s["kind"] for s in item["sources"]}
                item["sources"] += [s for s in sources if s["kind"] not in known]
                if primary.source == "simplify":
                    item["active"] = primary.active
                continue
            if not primary.active or not evaluate(primary, profile, now):
                continue
            matched += 1
            if key not in state.seen:
                new.append((primary, sources))

        stats["enriched"] = await _enrich(c, [j for j, _ in new], limits["enrich_per_run"])
        new_items = []
        for job, sources in new:
            if not evaluate(job, profile, now):  # description can't fail a gate, but be safe
                continue
            state.seen[job.key] = now
            recent = not job.posted_at or now - job.posted_at < limits["push_max_age_days"] * 86400
            if bootstrap and not recent:
                continue
            item = job.to_feed(now, sources)
            item["recent"] = recent
            state.feed[job.key] = item
            new_items.append(item)

        stats.update(matched=matched, new=len(new_items))
        stats["pushed"] = 0 if opt.dry_run else await _push(c, state, new_items, profile, limits, bootstrap, now)

    state.run += 1
    state.prune(now, limits["feed_days"])
    stats["duration_s"] = round(time.time() - t0, 1)
    stats["new_items"] = [f"{i['tier']}{i['score']:>3} {i['company']} — {i['title']}" for i in new_items]
    if not opt.dry_run:
        state.save(opt.state_path)
        write_feed(opt.feed_path, state, {k: v for k, v in stats.items() if k != "new_items"}, now)
    return stats


async def _push(c, state: State, items: list[dict], profile: Profile, limits: dict, bootstrap: bool, now: float) -> int:
    n = Notifier(c)
    if not n.enabled or not items:
        return 0
    if bootstrap:
        await n.send(
            {
                "title": "Job Radar is live",
                "message": f"Watching Simplify, levels.fyi and employer boards. {len(items)} matches from the last week are in the app.",
                "click": "jobradar://feed",
                "tags": ["satellite"],
            }
        )
        return n.sent
    today = time.strftime("%Y-%m-%d", time.gmtime(now))
    solo_tiers = set(profile.raw["push_individually"])
    solo, rest = [], []
    for item in sorted(items, key=lambda i: -i["score"]):
        if not item["recent"]:
            continue
        ok = item["tier"] in solo_tiers and "US citizenship/clearance" not in item["flags"]
        under_cap = len(solo) < limits["push_per_run"] and state.pushes.get(today, 0) + len(solo) < limits["push_per_day"]
        (solo if ok and under_cap else rest).append(item)
    for item in solo:
        await n.send(job_message(item))
    if rest:
        await n.send(summary_message(rest))
    state.pushes[today] = state.pushes.get(today, 0) + n.sent
    return n.sent


def github_token() -> str | None:
    if tok := os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"):
        return tok
    try:
        import subprocess

        return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5).stdout.strip() or None
    except Exception:
        return None
