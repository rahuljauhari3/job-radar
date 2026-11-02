"""Decide whether a job is relevant, and how relevant.

`evaluate` returns the job with tier/score/reasons/flags filled in, or None when
it fails a gate (not an internship, not in the US, wrong year, wrong field).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import yaml

from radar.models import Job

US_STATES = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas", "CA": "california",
    "CO": "colorado", "CT": "connecticut", "DE": "delaware", "FL": "florida", "GA": "georgia",
    "HI": "hawaii", "ID": "idaho", "IL": "illinois", "IN": "indiana", "IA": "iowa",
    "KS": "kansas", "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland",
    "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi",
    "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada", "NH": "new hampshire",
    "NJ": "new jersey", "NM": "new mexico", "NY": "new york", "NC": "north carolina",
    "ND": "north dakota", "OH": "ohio", "OK": "oklahoma", "OR": "oregon", "PA": "pennsylvania",
    "RI": "rhode island", "SC": "south carolina", "SD": "south dakota", "TN": "tennessee",
    "TX": "texas", "UT": "utah", "VT": "vermont", "VA": "virginia", "WA": "washington",
    "WV": "west virginia", "WI": "wisconsin", "WY": "wyoming", "DC": "district of columbia",
    "PR": "puerto rico",
}
US_CITIES = (
    "new york city", "nyc", "san francisco", "sf bay area", "bay area", "silicon valley",
    "seattle", "boston", "austin", "chicago", "los angeles", "atlanta", "denver", "pittsburgh",
    "san jose", "palo alto", "mountain view", "sunnyvale", "santa clara", "menlo park", "redwood city",
    "cupertino", "san mateo", "san diego", "irvine", "redmond", "bellevue", "kirkland", "houston",
    "dallas", "raleigh", "philadelphia", "new york", "miami", "phoenix", "salt lake city",
    "minneapolis", "detroit", "ann arbor", "columbus", "nashville", "charlotte", "baltimore",
    "san antonio", "orlando", "tampa", "boulder", "princeton", "arlington", "mclean", "reston",
)
US_ABBREVIATIONS = {"sf", "la", "nyc", "dc", "remote in usa", "remote us", "us remote"}
_STATE_CODE = re.compile(r"(?:,|\b)\s*(" + "|".join(US_STATES) + r")\b(?!\.\w)")
_US_WORDS = re.compile(r"\b(united states|usa|u\.s\.a?\.?|us|america)\b", re.I)
FOREIGN = re.compile(
    r"\b(canada|ontario|toronto|vancouver|montreal|quebec|british columbia|alberta|"
    r"united kingdom|uk|england|london|scotland|ireland|dublin|germany|berlin|munich|france|paris|"
    r"netherlands|amsterdam|spain|madrid|barcelona|italy|poland|warsaw|switzerland|zurich|sweden|"
    r"stockholm|denmark|norway|finland|portugal|lisbon|austria|belgium|czech|romania|hungary|"
    r"india|bengaluru|bangalore|hyderabad|pune|mumbai|delhi|chennai|gurgaon|gurugram|noida|"
    r"china|beijing|shanghai|shenzhen|hong kong|taiwan|taipei|japan|tokyo|korea|seoul|singapore|"
    r"malaysia|vietnam|philippines|indonesia|thailand|australia|sydney|melbourne|new zealand|"
    r"israel|tel aviv|uae|dubai|saudi|qatar|egypt|nigeria|kenya|south africa|brazil|mexico|"
    r"argentina|chile|colombia|costa rica|peru|emea|apac|latam|latin america|europe)\b",
    re.I,
)
_YEAR = re.compile(r"\b(20\d\d)\b")
_PHD = re.compile(r"\bph\.?d\b", re.I)
_MASTERS = re.compile(r"\b(ms|m\.s\.|master'?s?|graduate)\b", re.I)
_CITIZEN = re.compile(r"citizenship|clearance|citizen", re.I)
_CITIZEN_REQUIRED = re.compile(
    r"(must|required|requires|require|only)\W+(?:\w+\W+){0,6}?(u\.?s\.? citizen|security clearance)", re.I
)


def _phrase_regex(phrases: list[str]) -> list[tuple[str, re.Pattern, bool]]:
    """Compile phrases; returns (name, regex, needs_tech_context) triples."""
    out = []
    for p in phrases:
        needs_ctx = p.endswith("+")
        p = p.rstrip("+")
        prefix = p.endswith("*")
        name = p.rstrip("*")
        body = re.escape(name.lower()).replace(r"\ ", r"[\s\-_/]+")
        tail = "" if prefix else r"(?![a-z0-9+#])"
        out.append((name, re.compile(r"(?<![a-z0-9])" + body + tail), needs_ctx))
    return out


def _first_hit(text: str, rules, context: re.Pattern | None = None) -> str | None:
    for name, rx, needs_ctx in rules:
        if rx.search(text) and (not needs_ctx or (context and context.search(text))):
            return name
    return None


@dataclass
class Profile:
    raw: dict

    @classmethod
    def load(cls, path: str | Path) -> "Profile":
        return cls(yaml.safe_load(Path(path).read_text()))

    @cached_property
    def intern(self):
        return _phrase_regex(self.raw["intern_markers"])

    @cached_property
    def negative(self):
        return _phrase_regex(self.raw["negative_titles"])

    @cached_property
    def tiers(self):
        return [(t, _phrase_regex(self.raw[f"tier_{t.lower()}"])) for t in ("A", "B", "C")]

    @cached_property
    def tech_context(self):
        rules = _phrase_regex(self.raw["tech_context"])
        return re.compile("|".join(rx.pattern for _, rx, _ in rules))

    @cached_property
    def keywords(self):
        weights = self.raw["keywords"]
        return [(name, rx, weights[orig]) for (name, rx, _), orig in zip(_phrase_regex(list(weights)), weights)]


def is_us(location: str) -> bool | None:
    """True if clearly US, False if clearly elsewhere, None if unknown (e.g. bare 'Remote')."""
    loc = location.strip()
    if not loc:
        return None
    low = loc.lower()
    if FOREIGN.search(low):
        # Two-letter codes are ambiguous abroad ("Bengaluru, IN"), so only words count.
        return bool(re.search(r"united states|\busa\b", low) or any(c in low for c in US_CITIES))
    if _STATE_CODE.search(loc) or _US_WORDS.search(loc):
        return True
    if low in US_ABBREVIATIONS:
        return True
    if any(name in low for name in US_STATES.values()) or any(c in low for c in US_CITIES):
        return True
    return None


def _term_ok(job: Job, p: Profile, now: float) -> tuple[bool, str | None]:
    years_ok = set(p.raw["accepted_years"])
    years_bad = set(p.raw["rejected_years"])
    found = {int(y) for t in job.terms for y in _YEAR.findall(t)} | {int(y) for y in _YEAR.findall(job.title)}
    if found & years_ok:
        return True, None
    if found and found <= years_bad:
        return False, None
    max_age = p.raw["undated_max_age_days"] * 86400
    if job.posted_at and now - job.posted_at > max_age:
        return False, None
    return True, "term not stated"


def evaluate(job: Job, p: Profile, now: float | None = None) -> Job | None:
    now = now or time.time()
    title = job.title.lower()
    job.reasons, job.flags = [], []

    if job.source not in ("simplify", "simplify-pending") and not _first_hit(title, p.intern):
        return None
    if _first_hit(title, p.negative):
        return None

    us = [is_us(loc) for loc in job.locations]
    if us and not any(u is not False for u in us):
        return None
    if us and not any(us):
        job.flags.append("location unclear")

    ok, flag = _term_ok(job, p, now)
    if not ok:
        return None
    if flag:
        job.flags.append(flag)

    degrees = set(job.degrees)
    if degrees == {"PhD"} or (_PHD.search(title) and not _MASTERS.search(title)):
        return None

    tier = hit = None
    for name, rules in p.tiers:
        hit = _first_hit(title, rules, p.tech_context)
        if hit:
            tier = name
            job.reasons.append(f"title: “{hit}”")
            break
    if not tier and job.category in p.raw["fallback_categories"] and p.tech_context.search(title):
        tier = "C"
        job.reasons.append(f"Simplify category: {job.category}")
    if not tier:
        return None
    job.tier = tier

    score = p.raw["tier_base"][tier]
    desc = job.description.lower()
    if desc:
        hits = [(name, w) for name, rx, w in p.keywords if rx.search(desc)]
        hits.sort(key=lambda x: -x[1])
        boost = min(p.raw["keyword_cap"], sum(w for _, w in hits))
        if hits:
            score += boost
            job.reasons.append("JD mentions " + ", ".join(n for n, _ in hits[:8]))

    bonus, penalty = p.raw["bonus"], p.raw["penalty"]
    terms_low = " ".join(job.terms).lower() + " " + title
    if any(t in terms_low for t in p.raw["target_terms"]):
        score += bonus["target_term"]
        job.reasons.append("target term")
    if re.search(r"co-?op", terms_low):
        score += bonus["coop"]
        job.reasons.append("co-op")
    if "Master's" in degrees:
        score += bonus["masters_listed"]
    if job.category and "AI/ML" in job.category:
        score += bonus["ai_ml_category"]

    spons = job.sponsorship or ""
    if _CITIZEN.search(spons) or _CITIZEN_REQUIRED.search(desc):
        score -= penalty["citizenship"]
        job.flags.append("US citizenship/clearance")
    elif spons == "Does Not Offer Sponsorship":
        score -= penalty["no_sponsorship"]
        job.flags.append("no sponsorship")
    if degrees == {"Bachelor's"}:
        score -= penalty["bachelors_only"]
        job.flags.append("bachelor's only")

    job.score = max(0, min(100, score))
    return job
