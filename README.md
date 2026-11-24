# Job Radar

Watches internship and co-op postings in the US and pushes the relevant ones to your phone within a few hours of them appearing.

```
GitHub Actions, every ~3 h ─► radar (Python) ─► ntf-ai.app push ─► NTF-AI on iPhone (tap = apply)
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

1. `gh secret set NTFY_TOPIC` with a long random topic name (it is the only thing protecting your notifications). Pushes go to that topic on ntf-ai.app.
2. Create the clock before the first run: `gh api -X PUT 'repos/{owner}/{repo}/environments/radar-interval' -F wait_timer=180`. Every radar run starts `radar-timer.yml`, which sits out this 3-hour wait timer without holding a runner, then starts the next run. GitHub fires the workflow's own `schedule:` only a few times a day for this repo, so those runs are just extra polls and restart the chain if it breaks. To change the interval, change the wait timer (minutes).
3. Run the `radar` workflow once from the Actions tab (the first run bootstraps: one "Job Radar is live" push, no flood). That run also starts the chain.
4. Install [NTF-AI](https://apps.apple.com/app/id6787782178) (free, no account), allow notifications, then open `https://ntf-ai.app/<topic>` on the phone and confirm Subscribe. Job Radar's Settings has a Subscribe in NTF-AI button that opens the same link.
5. Run the `test-push` workflow from the Actions tab. It sends one "Job Radar test" notification to the secret's topic. If it shows inside NTF-AI but no banner appears, turn on iOS Settings → Notifications → NTF-AI. If it doesn't show even inside the app, the app is on a different topic. GitHub never shows a secret's value, so if you've lost it, set a new one and subscribe to that.

Job Radar used ntfy.sh and the official ntfy app until November 2026, when that app (1.7.0 on iOS 27) stopped showing pushes ([binwiederhier/ntfy#2117](https://github.com/binwiederhier/ntfy/issues/2117)). NTF-AI speaks the same protocol, which is why the secret is still called `NTFY_TOPIC`.

GitHub disables scheduled workflows in repositories with no activity for 60 days; push any commit to `main` to re-arm it.

## iOS app

See [`ios/README.md`](ios/README.md).
