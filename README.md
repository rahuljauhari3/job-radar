# Job Radar

Watches internship and co-op postings in the US and pushes the relevant ones to your phone within a few hours of them appearing.

```
GitHub Actions, every ~3 h ─► radar (Python) ─► ntfy push ─► iPhone (tap = apply)
                                   │
                                   └─► data branch: feed.json ─► Job Radar iOS app (feed + tracker)
```

## Sources

| Source | How | Notes |
|---|---|---|
| [Simplify Summer 2027 repo](https://github.com/SimplifyJobs/Summer2027-Internships) | `listings.json` (ETag) and open `new_internship` issues | Issues are pending submissions, the earliest signal |
| levels.fyi | Official free MCP server `https://mcp.levels.fyi/` (`search-jobs`, `get-job`) | Many postings link through to LinkedIn |
| Employer boards (Greenhouse, Lever, Ashby, SmartRecruiters) | Public job-board APIs, ~1,200 boards auto-discovered from Simplify URLs + `config/sources.yaml` watchlist | The employer-direct data HiringCafe indexes; often ahead of Simplify. A third of the boards per run |

HiringCafe and LinkedIn have no public API and block automated access, so they are not polled.

## Matching

`config/profile.yaml` holds every rule; edit it and the next run uses it.

- **Gates:** intern/co-op title, US location, a 2027/2028 term (or none stated and recent), not PhD-only, not a non-engineering field.
- **Tier A** core fit (ML systems, inference, performance, AI/infra, ML engineer), **B** good fit (SWE, data, cloud, research engineer, ML/AI), **C** stretch (GPU/compilers, firmware, quant, security, other engineering).
- **Score** = tier base + job-description keyword hits (vLLM, PyTorch, C++, NUMA, profiling, …) + target-term/co-op bonus − citizenship/sponsorship/bachelor's-only penalties. Reasons and flags travel with each job.
- A and B push one notification per posting (capped at 20 per run and 200 per day); C and the overflow arrive as one summary. Postings older than 7 days go to the feed without a push.

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
.venv/bin/python -m radar run --dry-run          # poll everything, print new matches, write nothing
NTFY_TOPIC=your-topic .venv/bin/python -m radar test-push
```

## Deploy

1. `gh secret set NTFY_TOPIC` with a long random topic name (it is the only thing protecting your notifications).
2. Create the clock before the first run: `gh api -X PUT 'repos/{owner}/{repo}/environments/radar-interval' -F wait_timer=180`. Every radar run starts `radar-timer.yml`, which sits out this 3-hour wait timer without holding a runner, then starts the next run. GitHub fires the workflow's own `schedule:` only a few times a day for this repo, so those runs are just extra polls and restart the chain if it breaks. To change the interval, change the wait timer (minutes).
3. Run the `radar` workflow once from the Actions tab (the first run bootstraps: one "Job Radar is live" push, no flood). That run also starts the chain.
4. Install the official [ntfy iOS app](https://apps.apple.com/app/ntfy/id1625396347) and subscribe to the same topic on `ntfy.sh`. Third-party clients that default to another server (ntfy-me.com, for one) never see these messages.

GitHub disables scheduled workflows in repositories with no activity for 60 days; push any commit to `main` to re-arm it.

## iOS app

See [`ios/README.md`](ios/README.md).
