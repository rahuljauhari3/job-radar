"""SimplifyJobs internship repo: merged listings plus pending submissions.

Pending submissions are open issues labeled `new_internship`; the Simplify bot
turns them into listings later, so they are the earliest signal.
"""

from __future__ import annotations

import re
from datetime import datetime

import httpx

from radar.http import request
from radar.models import Job


def listings_url(repo: str, branch: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{branch}/.github/scripts/listings.json"


async def fetch_listings(c: httpx.AsyncClient, repo: str, branch: str, etag: str | None):
    """Returns (raw_rows or None if unchanged, new etag)."""
    headers = {"If-None-Match": etag} if etag else {}
    r = await request(c, "GET", listings_url(repo, branch), headers=headers)
    if r.status_code == 304:
        return None, etag
    r.raise_for_status()
    return r.json(), r.headers.get("ETag")


def parse_listing(x: dict) -> Job | None:
    if not x.get("is_visible", True) or not x.get("url"):
        return None
    return Job(
        source="simplify",
        source_id=x["id"],
        company=x.get("company_name", "").strip(),
        title=x.get("title", "").strip(),
        url=x["url"].replace("?embed=true", "").replace("&embed=true", ""),
        locations=x.get("locations") or [],
        terms=[t for t in x.get("terms") or [] if t and t != "N/A"],
        posted_at=x.get("date_posted"),
        sponsorship=x.get("sponsorship"),
        degrees=x.get("degrees") or [],
        category=x.get("category"),
        active=bool(x.get("active", True)),
    )


async def fetch_pending(c: httpx.AsyncClient, repo: str, label: str, token: str | None) -> list[Job]:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = await request(
        c,
        "GET",
        f"https://api.github.com/repos/{repo}/issues",
        params={"labels": label, "state": "open", "per_page": 100, "sort": "created", "direction": "desc"},
        headers=headers,
    )
    r.raise_for_status()
    return [j for j in (parse_issue(i) for i in r.json() if "pull_request" not in i) if j]


_SECTION = re.compile(r"^###\s+(.+?)\s*$\n+(.*?)(?=^###\s|\Z)", re.M | re.S)


def issue_fields(body: str) -> dict[str, str]:
    return {k.strip().lower(): v.strip() for k, v in _SECTION.findall(body or "")}


def _get(fields: dict[str, str], *prefixes: str) -> str:
    for k, v in fields.items():
        if any(k.startswith(p) for p in prefixes):
            return "" if v == "_No response_" else v
    return ""


def parse_issue(issue: dict) -> Job | None:
    f = issue_fields(issue.get("body") or "")
    url = _get(f, "link to")
    title = _get(f, "internship title", "job title", "title")
    company = _get(f, "company name", "company")
    if not (url and title and company) or _get(f, "is this internship currently accepting").lower() == "no":
        return None
    degrees = ["Master's", "PhD"] if "[x]" in _get(f, "advanced degree").lower() else []
    created = issue.get("created_at")
    return Job(
        source="simplify-pending",
        source_id=str(issue["number"]),
        company=company,
        title=title,
        url=url.split()[0],
        locations=[s.strip() for s in re.split(r"[|;\n]", _get(f, "location")) if s.strip()],
        terms=[s.strip() for s in re.split(r"[,\n]", _get(f, "what term")) if s.strip()],
        posted_at=datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp() if created else None,
        sponsorship=_get(f, "does this internship offer sponsorship") or None,
        degrees=degrees,
        category=_get(f, "what category") or None,
    )
