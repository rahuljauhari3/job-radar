"""The unified job record every source produces."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field

_COMPANY_SUFFIX = re.compile(r"\b(inc|llc|ltd|corp|corporation|co|company|plc|gmbh|lp|l\.p)\b\.?", re.I)
_TERM_NOISE = re.compile(
    r"\(?\b(spring|summer|fall|autumn|winter)?\s*(20\d\d)\b\)?|\b(intern(ship)?|co-?op)s?\b", re.I
)
_NON_WORD = re.compile(r"[^a-z0-9+#]+")


_TITLE_STOPWORDS = {
    "intern", "interns", "internship", "co", "op", "coop", "summer", "fall", "spring", "winter",
    "ms", "phd", "bs", "masters", "master", "s", "the", "and", "of", "for", "in", "a", "an", "to",
    "program", "student", "students", "graduate", "undergraduate", "university", "2025", "2026",
    "2027", "2028", "i", "ii", "iii",
}


def norm_company(name: str) -> str:
    """Short company token: 'Samsung Semiconductor, Inc.' and 'Samsung' both give 'samsung'."""
    words = _NON_WORD.sub(" ", _COMPANY_SUFFIX.sub(" ", name.lower())).split()
    words = [w for w in words if w != "the"] or ["?"]
    return " ".join(words[:2]) if len(words[0]) <= 3 and len(words) > 1 else words[0]


def norm_title(title: str) -> str:
    """Order-free set of meaningful title words, so reworded duplicates collide."""
    title = _TERM_NOISE.sub(" ", title.lower())
    words = set(_NON_WORD.sub(" ", title).split()) - _TITLE_STOPWORDS
    return " ".join(sorted(words))


@dataclass
class Job:
    source: str  # simplify, simplify-pending, levels, greenhouse, lever, ashby, smartrecruiters
    source_id: str
    company: str
    title: str
    url: str
    locations: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)
    posted_at: float | None = None  # unix seconds
    sponsorship: str | None = None
    degrees: list[str] = field(default_factory=list)
    category: str | None = None
    description: str = ""
    active: bool = True
    # Filled in by the matcher.
    tier: str | None = None
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Same posting across sources (and across its Summer/Fall variants) shares a key."""
        raw = f"{norm_company(self.company)}|{norm_title(self.title)}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]

    def to_feed(self, first_seen: float, sources: list[dict]) -> dict:
        d = asdict(self)
        d.pop("description")
        d.pop("source")
        d.pop("source_id")
        d["id"] = self.key
        d["snippet"] = _snippet(self.description)
        d["first_seen"] = first_seen
        d["sources"] = sources
        return d


def _snippet(text: str, limit: int = 700) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"
