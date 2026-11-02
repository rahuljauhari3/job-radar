"""Employer career boards through each ATS's public job-board API.

This is the same employer-direct data HiringCafe indexes. Boards are discovered
from Simplify posting URLs, so any company that has ever listed an internship
on Simplify is watched directly.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime

import httpx

from radar.http import html_to_text, request
from radar.models import Job

PLATFORMS = ("greenhouse", "lever", "ashby", "smartrecruiters")

_URL_PATTERNS = {
    "greenhouse": re.compile(
        r"greenhouse\.io/(?:embed/job_app\?for=|embed/job_board\?for=)?([\w-]+)(?:/jobs/(\d+))?", re.I
    ),
    "lever": re.compile(r"jobs\.lever\.co/([\w.-]+)(?:/([0-9a-f-]{36}))?", re.I),
    "ashby": re.compile(r"jobs\.ashbyhq\.com/([^/?#]+)(?:/([0-9a-f-]{36}))?", re.I),
    "smartrecruiters": re.compile(r"smartrecruiters\.com/([\w-]+)(?:/(\d+))?", re.I),
}
_TERM_WORDS = re.compile(r"\b(spring|summer|fall|autumn|winter|20\d\d|co-?op)\b", re.I)
_NOT_SLUGS = {"embed", "v1", "jobs", "job-boards", "boards", "api"}


def parse_url(url: str) -> tuple[str, str, str | None] | None:
    """(platform, board slug, job id or None) for a known ATS URL."""
    for platform, rx in _URL_PATTERNS.items():
        m = rx.search(url or "")
        if m and m.group(1).lower() not in _NOT_SLUGS:
            if platform == "greenhouse" and "gh_jid=" in url:
                return platform, m.group(1), re.search(r"gh_jid=(\d+)", url).group(1)
            return platform, m.group(1), m.group(2)
    return None


def discover_boards(rows: list[dict], watchlist: dict) -> dict[str, dict[str, str]]:
    boards: dict[str, dict[str, str]] = {p: {} for p in PLATFORMS}
    for x in rows:
        hit = parse_url(x.get("url", ""))
        if hit:
            boards[hit[0]].setdefault(hit[1], x.get("company_name") or hit[1])
    for platform, entries in (watchlist or {}).items():
        boards.setdefault(platform, {}).update(entries or {})
    return boards


def rotation_slice(boards: dict[str, dict[str, str]], run: int, rotation: int):
    flat = sorted((p, slug, name) for p, entries in boards.items() for slug, name in entries.items())
    return [b for i, b in enumerate(flat) if i % rotation == run % rotation]


def _ts(s: str | None) -> float | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


async def fetch_board(c: httpx.AsyncClient, platform: str, slug: str, company: str) -> list[Job]:
    if platform == "greenhouse":
        r = await request(c, "GET", f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return [
            Job(
                source="greenhouse",
                source_id=str(j["id"]),
                company=j.get("company_name") or company,
                title=j.get("title", "").strip(),
                url=j.get("absolute_url", ""),
                locations=[s.strip() for s in re.split(r"[|;]", (j.get("location") or {}).get("name") or "") if s.strip()],
                posted_at=_ts(j.get("first_published") or j.get("updated_at")),
            )
            for j in r.json().get("jobs", [])
        ]
    if platform == "lever":
        r = await request(c, "GET", f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
        if r.status_code == 404:
            return []
        r.raise_for_status()
        out = []
        for j in r.json():
            cat = j.get("categories") or {}
            locs = cat.get("allLocations") or ([cat["location"]] if cat.get("location") else [])
            desc = "\n".join(
                [j.get("descriptionPlain", "")]
                + [f"{l.get('text', '')}\n{html_to_text(l.get('content', ''))}" for l in j.get("lists", [])]
            )
            out.append(
                Job(
                    source="lever",
                    source_id=j["id"],
                    company=company,
                    title=j.get("text", "").strip(),
                    url=j.get("hostedUrl", ""),
                    locations=locs,
                    terms=[cat["commitment"]] if _TERM_WORDS.search(cat.get("commitment") or "") else [],
                    posted_at=j["createdAt"] / 1000 if j.get("createdAt") else None,
                    description=desc,
                )
            )
        return out
    if platform == "ashby":
        r = await request(c, "GET", f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
        if r.status_code == 404:
            return []
        r.raise_for_status()
        out = []
        for j in r.json().get("jobs", []):
            if j.get("isListed") is False:
                continue
            locs = [j.get("location", "")] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
            out.append(
                Job(
                    source="ashby",
                    source_id=j["id"],
                    company=company,
                    title=j.get("title", "").strip(),
                    url=j.get("jobUrl", ""),
                    locations=[l for l in locs if l],
                    posted_at=_ts(j.get("publishedAt")),
                    description=j.get("descriptionPlain", ""),
                )
            )
        return out
    if platform == "smartrecruiters":
        r = await request(
            c,
            "GET",
            f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
            params={"country": "us", "q": "intern", "limit": 100},
        )
        if r.status_code == 404:
            return []
        r.raise_for_status()
        out = []
        for j in r.json().get("content", []):
            loc = j.get("location") or {}
            out.append(
                Job(
                    source="smartrecruiters",
                    source_id=str(j["id"]),
                    company=(j.get("company") or {}).get("name") or company,
                    title=j.get("name", "").strip(),
                    url=f"https://jobs.smartrecruiters.com/{slug}/{j['id']}",
                    locations=[loc.get("fullLocation") or ", ".join(filter(None, [loc.get("city"), loc.get("region"), "US"]))],
                    posted_at=_ts(j.get("releasedDate")),
                )
            )
        return out
    raise ValueError(platform)


async def fetch_boards(c: httpx.AsyncClient, batch, concurrency: int = 16):
    """Returns (jobs, error count)."""
    sem = asyncio.Semaphore(concurrency)
    errors = 0

    async def one(platform, slug, name):
        nonlocal errors
        async with sem:
            try:
                return await fetch_board(c, platform, slug, name)
            except Exception:  # one broken board must not sink the run
                errors += 1
                return []

    results = await asyncio.gather(*(one(*b) for b in batch))
    return [j for js in results for j in js], errors


async def describe(c: httpx.AsyncClient, url: str, cache: dict | None = None) -> str:
    """Full job description for a posting URL on a supported ATS, else ''.

    `cache` holds whole Ashby boards for the run, since Ashby has no per-job endpoint.
    """
    hit = parse_url(url)
    if not hit or not hit[2]:
        return ""
    platform, slug, jid = hit
    if platform == "greenhouse":
        r = await request(c, "GET", f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{jid}")
        return html_to_text(r.json().get("content", "")) if r.is_success else ""
    if platform == "lever":
        r = await request(c, "GET", f"https://api.lever.co/v0/postings/{slug}/{jid}")
        if not r.is_success:
            return ""
        j = r.json()
        return "\n".join([j.get("descriptionPlain", "")] + [html_to_text(l.get("content", "")) for l in j.get("lists", [])])
    if platform == "ashby":
        cache = {} if cache is None else cache
        if slug not in cache:
            r = await request(c, "GET", f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
            cache[slug] = r.json().get("jobs", []) if r.is_success else []
        for j in cache[slug]:
            if j.get("id") == jid:
                return j.get("descriptionPlain", "")
        return ""
    if platform == "smartrecruiters":
        r = await request(c, "GET", f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{jid}")
        if not r.is_success:
            return ""
        sections = (r.json().get("jobAd") or {}).get("sections") or {}
        return "\n".join(html_to_text((sections.get(k) or {}).get("text", "")) for k in ("jobDescription", "qualifications"))
    return ""
