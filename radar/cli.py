"""Command line: `python -m radar run` polls once; `python -m radar test-push` checks ntfy."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from radar import http
from radar.notify import Notifier
from radar.pipeline import Options, github_token, run


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="radar")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="poll every source once")
    r.add_argument("--config", type=Path, default=Path("config"))
    r.add_argument("--state", type=Path, default=Path("data/state.json"))
    r.add_argument("--feed", type=Path, default=Path("data/feed.json"))
    r.add_argument("--dry-run", action="store_true", help="no pushes, nothing written")
    r.add_argument("--bootstrap", action="store_true", help="mark everything seen without per-job pushes")
    r.add_argument("--only", default="simplify,levels,ats", help="comma-separated: simplify,levels,ats")
    r.add_argument("--show", type=int, default=25, help="print this many new matches")

    t = sub.add_parser("test-push", help="send one test notification to NTFY_TOPIC")
    t.add_argument("--topic")

    args = ap.parse_args(argv)
    if args.cmd == "test-push":
        return asyncio.run(_test_push(args.topic))

    opt = Options(
        config_dir=args.config,
        state_path=args.state,
        feed_path=args.feed,
        dry_run=args.dry_run,
        bootstrap=args.bootstrap,
        only=set(args.only.split(",")),
        github_token=github_token(),
    )
    stats = asyncio.run(run(opt))
    items = stats.pop("new_items")
    print(json.dumps(stats, indent=1))
    for line in items[: args.show]:
        print(" ", line)
    if len(items) > args.show:
        print(f"  … {len(items) - args.show} more")
    return 0


async def _test_push(topic: str | None) -> int:
    async with http.client() as c:
        n = Notifier(c, topic=topic)
        if not n.enabled:
            print("Set NTFY_TOPIC or pass --topic")
            return 1
        ok = await n.send({"title": "Job Radar test", "message": "Notifications are working.", "tags": ["white_check_mark"]})
        print("sent" if ok else "failed")
        return 0 if ok else 1
