import json
from pathlib import Path

from radar.models import Job
from radar.sources import ats, levels, simplify

FX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FX / name).read_text())


def test_parse_listing():
    rows = load("simplify_listings.json")
    jobs = [j for j in map(simplify.parse_listing, rows) if j]
    assert len(jobs) == len(rows)
    j = jobs[0]
    assert j.source == "simplify" and j.company and j.title and j.url.startswith("http")
    assert "embed=true" not in "".join(x.url for x in jobs)
    assert any(not x.active for x in jobs)


def test_parse_issue():
    jobs = [j for j in map(simplify.parse_issue, load("simplify_issues.json")) if j]
    assert jobs
    j = jobs[0]
    assert j.source == "simplify-pending"
    assert j.url.startswith("http") and j.company and j.title and j.terms and j.posted_at


def test_issue_fields_handles_no_response():
    body = "### Link to Internship Posting\n\nhttps://a.b/c\n\n### Company Name\n\nAcme\n\n### Internship Title\n\nSWE Intern\n\n### Location\n\nBoston, MA | NYC\n\n### What term(s) is this internship offered for?\n\nSummer 2027, Fall 2027\n\n### Advanced Degree Requirements\n\n- [x] requires\n\n### Email\n\n_No response_"
    j = simplify.parse_issue({"number": 1, "body": body, "created_at": "2026-11-02T04:11:46Z"})
    assert j.locations == ["Boston, MA", "NYC"]
    assert j.terms == ["Summer 2027", "Fall 2027"]
    assert j.degrees == ["Master's", "PhD"]


def test_levels_parse():
    rpc = levels._parse_rpc((FX / "levels_search.sse").read_text())
    page = json.loads(rpc["result"]["content"][0]["text"])
    jobs = [levels.parse_job(j) for j in page["jobs"]]
    assert jobs and all(j.source == "levels" and j.url.startswith("http") and j.posted_at for j in jobs)


def test_parse_url():
    assert ats.parse_url("https://job-boards.greenhouse.io/anthropic/jobs/5456619008") == ("greenhouse", "anthropic", "5456619008")
    assert ats.parse_url("https://boards.greenhouse.io/embed/job_app?for=acme&token=1") == ("greenhouse", "acme", None)
    assert ats.parse_url("https://jobs.lever.co/palantir/6ed76ce8-4156-4b60-b120-403538bd66cd/apply")[2] == "6ed76ce8-4156-4b60-b120-403538bd66cd"
    assert ats.parse_url("https://jobs.ashbyhq.com/metalenz/c8150d66-9f72-4508-ac94-8a7efa54e206/application?embed=true")[:2] == ("ashby", "metalenz")
    assert ats.parse_url("https://jobs.smartrecruiters.com/WesternDigital/744000113396537") == ("smartrecruiters", "WesternDigital", "744000113396537")
    assert ats.parse_url("https://acme.wd1.myworkdayjobs.com/x") is None


def test_discover_boards_and_rotation():
    boards = ats.discover_boards(load("simplify_listings.json"), {"greenhouse": {"anthropic": "Anthropic"}})
    assert boards["greenhouse"]["anthropic"] == "Anthropic"
    flat = sum(len(v) for v in boards.values())
    slices = [ats.rotation_slice(boards, run, 3) for run in range(3)]
    assert sum(map(len, slices)) == flat
    assert not set(slices[0]) & set(slices[1])


BOARDS = [
    ("greenhouse", "anthropic", "Anthropic"),
    ("lever", "palantir", "Palantir"),
    ("ashby", "ramp", "Ramp"),
    ("smartrecruiters", "BoschGroup", "Bosch"),
    ("greenhouse", "gone", "Gone"),
    ("lever", "broken", "Broken"),
]


def test_fetch_boards_with_fixtures(respx_mock):
    respx_mock.get("https://boards-api.greenhouse.io/v1/boards/anthropic/jobs").respond(json=load("greenhouse_board.json"))
    respx_mock.get("https://api.lever.co/v0/postings/palantir").respond(json=load("lever_board.json"))
    respx_mock.get("https://api.ashbyhq.com/posting-api/job-board/ramp").respond(json=load("ashby_board.json"))
    respx_mock.get(url__startswith="https://api.smartrecruiters.com/v1/companies/BoschGroup/postings").respond(
        json=load("smartrecruiters_board.json")
    )
    respx_mock.get("https://boards-api.greenhouse.io/v1/boards/gone/jobs").respond(404)
    respx_mock.get("https://api.lever.co/v0/postings/broken").respond(json={"unexpected": True})
    import asyncio

    import httpx

    async def go():
        async with httpx.AsyncClient() as c:
            return await ats.fetch_boards(c, BOARDS)

    jobs, errors = asyncio.run(go())
    by_src = {s: [j for j in jobs if j.source == s] for s in ats.PLATFORMS}
    assert len(by_src["greenhouse"]) == 5 and by_src["greenhouse"][0].company == "Anthropic"
    assert len(by_src["lever"]) == 3 and by_src["lever"][0].description
    assert len(by_src["ashby"]) == 3 and all(j.locations for j in by_src["ashby"])
    assert len(by_src["smartrecruiters"]) == 3
    assert errors == 1  # the malformed Lever board; 404 just means no jobs
    assert all(isinstance(j, Job) and j.url.startswith("https://") for j in jobs)
