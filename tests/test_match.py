import time

import pytest

from radar.match import Profile, evaluate, is_us
from radar.models import Job

P = Profile.load("config/profile.yaml")
NOW = time.time()


def job(title, source="greenhouse", **kw):
    kw.setdefault("locations", ["Boston, MA"])
    kw.setdefault("terms", ["Summer 2027"])
    kw.setdefault("posted_at", NOW - 3600)
    return Job(source=source, source_id="1", company=kw.pop("company", "Acme"), title=title, url="https://x", **kw)


@pytest.mark.parametrize(
    "title,tier",
    [
        ("Machine Learning Engineer Intern", "A"),
        ("ML Infrastructure Intern", "A"),
        ("Software Engineer Intern - LLM Inference", "A"),
        ("Performance Engineering Intern", "A"),
        ("Software Engineer Intern - Recommendation Infra - Performance Efficiency", "A"),
        ("AI Engineer Co-op", "A"),
        ("Software Engineer Intern", "B"),
        ("Flight Software Intern", "B"),
        ("Data Engineer Intern", "B"),
        ("Site Reliability Engineering Intern", "B"),
        ("Software Engineer Intern - MS/PhD", "B"),
        ("Forward Deployed Engineer Intern", "B"),
        ("GPU Compiler Intern", "C"),
        ("Quantitative Research Intern", "C"),
        ("Firmware Engineer Intern", "C"),
    ],
)
def test_tiers(title, tier):
    assert evaluate(job(title), P, NOW).tier == tier


@pytest.mark.parametrize(
    "title",
    [
        "Product Design Intern",
        "Marketing Intern",
        "Mechanical Engineering Intern",
        "Business Performance & Analytics Intern",
        "Critical Infrastructure Analysis Intern",
        "Research Scientist Intern - PhD",
        "Field Engineer Intern - Infrastructure Management",
        "Senior Software Engineer",  # ATS title without an intern marker
    ],
)
def test_dropped_titles(title):
    assert evaluate(job(title), P, NOW) is None


def test_simplify_rows_skip_intern_marker():
    assert evaluate(job("Software Engineer - Summer", source="simplify"), P, NOW)


def test_location_gate():
    assert evaluate(job("Software Engineer Intern", locations=["Toronto, ON, Canada"]), P, NOW) is None
    assert evaluate(job("Software Engineer Intern", locations=["London, UK", "New York, NY"]), P, NOW)
    unclear = evaluate(job("Software Engineer Intern", locations=["Remote"]), P, NOW)
    assert "location unclear" in unclear.flags


@pytest.mark.parametrize(
    "loc,expected",
    [
        ("Boston, MA", True),
        ("SF", True),
        ("Remote in USA", True),
        ("Mountain View, CA, USA", True),
        ("Bengaluru, IN", False),
        ("Waterloo, ON, Canada", False),
        ("Remote", None),
    ],
)
def test_is_us(loc, expected):
    assert is_us(loc) is expected


def test_term_gate():
    assert evaluate(job("Software Engineer Intern", terms=["Summer 2026"]), P, NOW) is None
    assert evaluate(job("Software Engineer Intern - Fall 2026", terms=[]), P, NOW) is None
    assert evaluate(job("Software Engineer Intern", terms=["Fall 2026", "Spring 2027"]), P, NOW)
    old = job("Software Engineer Intern", terms=[], posted_at=NOW - 90 * 86400)
    assert evaluate(old, P, NOW) is None
    assert "term not stated" in evaluate(job("Software Engineer Intern", terms=[]), P, NOW).flags


def test_phd_only_dropped():
    assert evaluate(job("Software Engineer Intern", degrees=["PhD"]), P, NOW) is None
    assert evaluate(job("Software Engineer Intern", degrees=["Master's", "PhD"]), P, NOW)


def test_description_keywords_raise_score():
    plain = evaluate(job("Software Engineer Intern"), P, NOW).score
    rich = evaluate(job("Software Engineer Intern", description="vLLM, PyTorch, NUMA and C++ profiling"), P, NOW)
    assert rich.score > plain
    assert any("vllm" in r for r in rich.reasons)


def test_citizenship_penalty_and_flag():
    j = evaluate(job("Software Engineer Intern", sponsorship="U.S. Citizenship is Required"), P, NOW)
    assert "US citizenship/clearance" in j.flags
    j2 = evaluate(job("Software Engineer Intern", description="Applicants must be a U.S. citizen."), P, NOW)
    assert "US citizenship/clearance" in j2.flags
    assert j2.score < evaluate(job("Software Engineer Intern"), P, NOW).score


def test_category_fallback_needs_tech_word():
    assert evaluate(job("Research Intern - Model Shaping", source="simplify", category="AI/ML/Data"), P, NOW).tier == "C"
    assert evaluate(job("Claims Intern", source="simplify", category="Software"), P, NOW) is None
