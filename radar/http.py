"""Shared HTTP client with polite retries."""

from __future__ import annotations

import asyncio
import re

import httpx

USER_AGENT = "job-radar/0.1 (+https://github.com/rahuljauhari3/job-radar)"


def client(**kw) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(30, connect=10),
        limits=httpx.Limits(max_connections=24),
        follow_redirects=True,
        **kw,
    )


async def request(c: httpx.AsyncClient, method: str, url: str, tries: int = 3, **kw) -> httpx.Response:
    for attempt in range(tries):
        try:
            r = await c.request(method, url, **kw)
        except httpx.TransportError:
            if attempt == tries - 1:
                raise
        else:
            if r.status_code not in (429, 500, 502, 503, 504) or attempt == tries - 1:
                return r
        await asyncio.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


_TAG = re.compile(r"<[^>]+>")


def html_to_text(s: str) -> str:
    import html

    s = html.unescape(s or "")  # Greenhouse double-escapes its HTML
    s = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", "\n", s, flags=re.I)
    return html.unescape(_TAG.sub(" ", s))
