"""Poller state between runs (seen postings, ETags, boards) and the published feed."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

SEEN_TTL_DAYS = 180


@dataclass
class State:
    seen: dict[str, float] = field(default_factory=dict)  # job key -> first seen
    feed: dict[str, dict] = field(default_factory=dict)  # job key -> feed item
    etags: dict[str, str] = field(default_factory=dict)
    boards: dict[str, dict[str, str]] = field(default_factory=dict)
    pushes: dict[str, int] = field(default_factory=dict)  # UTC date -> count
    run: int = 0

    @property
    def is_new(self) -> bool:
        return not self.seen

    @classmethod
    def load(cls, path: Path) -> "State":
        if not path.exists():
            return cls()
        d = json.loads(path.read_text())
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, json.dumps(self.__dict__, separators=(",", ":")))

    def prune(self, now: float, feed_days: int):
        self.feed = {k: v for k, v in self.feed.items() if now - v["first_seen"] < feed_days * 86400}
        self.seen = {k: t for k, t in self.seen.items() if now - t < SEEN_TTL_DAYS * 86400}
        today = time.strftime("%Y-%m-%d", time.gmtime(now))
        self.pushes = {d: n for d, n in self.pushes.items() if d == today}


def write_feed(path: Path, state: State, stats: dict, now: float):
    jobs = sorted(state.feed.values(), key=lambda j: (-j["first_seen"], -j["score"]))
    _atomic_write(
        path,
        json.dumps({"version": 1, "generated_at": now, "stats": stats, "jobs": jobs}, ensure_ascii=False, indent=1),
    )


def _atomic_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)
