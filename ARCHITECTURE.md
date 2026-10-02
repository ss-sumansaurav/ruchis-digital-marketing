# Architecture and build status

## Runtime
**Recommendation: Claude Code, with the agents as project subagents.** Each agent is a Markdown file with a short YAML header (name, description, allowed tools) and its instructions as the body. Reasons:

- The files are plain text, so you can read and edit every agent, and they can be moved to another agent framework later.
- The CEO runs as the main session and is the only agent that talks to you. Subagents cannot ask the user questions, which enforces "only the CEO talks to the Principal".
- The CEO's tool list allows it to delegate only to the seven department heads (plus the ad hoc reporting analyst). Heads delegate to specialists. Claude Code's documentation states that subagents can spawn their own subagents up to three layers below the main session by default in current versions; this design uses two.
- Each agent gets only the tools it needs. The compliance and QA reviewers cannot write files.

Reference: https://code.claude.com/docs/en/sub-agents

**Tested in Claude Code (2.1.287) on 2 Oct 2026.** Headless runs from this folder confirmed: the main session starts as the CEO, all agents in the subfolders load, and the CEO can delegate to the seven heads. Two findings:

1. Nesting depth. Claude Code reads `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`; some environments set it to 1, which silently strips the Agent tool from the heads. `.claude/settings.json` now sets it to 2 (heads may delegate, specialists may not), and with that a head does get its Agent tool.
2. The CEO's agent allowlist bounds the whole tree: with the CEO limited to the heads, a head's own Agent tool offered only those same names. With Suman's approval (2 Oct 2026) the CEO now has an unrestricted Agent tool and an instruction never to call specialists directly; each head's tool names only its own team. Verified the same day: CEO > head-of-media-planning > media-planner returned READY.

## Organisation

    Principal (human): approves all spend
      CEO
        Client Services Director ....... Account Manager, Project Manager
        Chief Strategy Officer ......... Audience and Insights Analyst, Competitive Analyst
        Head of Media Planning ......... Media Planner, Budget and Forecasting Analyst
        Head of Performance ............ Paid Search, Paid Social, Programmatic, Retail Media,
                                         SEO, CRM and Lifecycle, Influencer and Affiliate, Ad Operations
        Head of Creative ............... Copywriter, Designer, Video Producer, CRO Specialist
        Head of Marketing Science ...... Data Engineer, Performance Analyst, Attribution Analyst,
                                         Dashboard Developer, Ad Hoc Reporting Analyst
        Head of Finance and Governance . Budget Controller, Compliance Reviewer, QA Reviewer

## The approval gate

    CEO registers request -> you approve with your key -> Ad Operations submits action
                                                              |
                                              execution service checks the approval record
                                                              |
                                          match: call ad platform     no match: BLOCKED and logged

What the code enforces (`agency/core.py`, proven by `tests/test_gate.py`):

- A launch, budget increase or flight extension runs only against an APPROVED request matching channel, campaign, dates, total amount and daily cap.
- Approving, modifying or rejecting needs your key. Only a salted hash is stored.
- Approvals cannot add up past the client ceiling.
- Pauses and budget decreases always go through.
- Unknown action types are refused.
- Every request, decision, executed action and blocked action is written to an audit log.

An approval with campaign `*` is an envelope: Ad Operations may launch and rebalance several campaigns under it, as long as the total and the daily cap hold. Moving money between two approvals (for example between channels) always needs a new request; a reallocation tolerance is not implemented yet.

**Telegram approvals** (`agency/telegram.py`). Agents only create requests. A separate bot process sends each pending request to Ruchi's bound Telegram chat with APPROVE and REJECT buttons, and records her decision through the gate. A decision counts only if it comes from her Telegram user id, carries the bot's approval secret (issued once when she binds the account with her key) and matches the one-time nonce of the message sent for that request. From Telegram, MODIFY can only lower a request. Proven by `tests/test_telegram.py` (17 tests). The bot uses long polling, so it runs on a laptop or small server with no public address. The risk to weigh: anyone holding her unlocked phone can approve, so turn on Telegram's passcode lock and two-step verification.

**Limit you should know about.** In this dry-run setup the gate's state file sits on the same machine as the agents. The key stops an agent recording an approval through the gate, but it does not stop a process with file access from tampering with the state file directly. Before live use, the execution service must run as a separate service that alone holds the ad platform write credentials and its own state, out of the agents' reach. Agents then have no route to a platform except through it.

## Data and reporting

    ad platforms, web analytics, CRM, media plan, approval gate state
        -> extracts (today: pipeline/synth.py; live: dlt or Meltano, read-only credentials)
        -> pipeline/ingest.py -> raw.* in DuckDB (state/<client>.duckdb)
        -> dbt Core project in warehouse/: staging -> core.fct_performance_daily -> marts.*
           every metric defined once in warehouse/macros/metrics.sql
        -> pipeline/dashboard.py -> workspace/<client>/dashboard.html (interim, static)
           hosted Superset / Metabase OSS / Grafana later, reading the same marts
        -> pipeline/adhoc.py runs saved queries in reports/queries/ read-only

One command runs it: `python -m pipeline.run --client <client> --synthetic` (dry run) or `--extracts <dir>`.

Marts: exec overview, campaign performance (pacing, KPI against target, spend forecast range), channel performance and daily, funnel, approvals, reconciliation (platform spend against the ledger), alerts, freshness.

Alert rules: unapproved spend (a campaign spending with no gate launch behind it, for example one set up directly in the platform), overspend, budget exhaustion before flight end, pacing deviation beyond `pacing_tolerance_pct`, platform CPA spike (last 3 days against the 7 before, at least 20 conversions), tracking break (clicks but no sessions), reconciliation beyond `reconciliation_tolerance_pct`, approval breach (should be impossible; it checks the gate).

Measurement honesty is built into the metric layer: platform-reported conversions and CRM ("backend") orders sit in separate columns, backend metrics divide only by spend on days the CRM export covers, and neither is labelled incremental. Incrementality needs experiments or MMM (still to build).

Dashboard views: executive overview (budget, pacing, KPIs against target, forecast), channel and campaign performance, funnel, approvals, alerts. Every tile shows a data-as-of time, because ad platform reporting lags.

Other open-source candidates: Robyn, Meridian, PyMC-Marketing (media mix modelling); Prophet, statsmodels, SciPy, OR-Tools (forecasting, optimisation); GeoLift, CausalImpact, GrowthBook (experiments); ChannelAttribution; Matomo, PostHog, Plausible (analytics); Mautic, listmonk (email); Lighthouse (site audits); Penpot, Inkscape, GIMP, FFmpeg (creative); Airflow, Dagster, Prefect (scheduling). Licences and maintenance status were not re-verified during this build; the agents are instructed to verify before adopting each one.

## Build status

| Step in BUILD_PROMPT.md | Status |
|---|---|
| 1. Architecture note | Done (this file) |
| 2. Agent definitions | Done: 34 agents. Not yet run in Claude Code |
| 3. Orchestration, shared workspace, logging | Partly: CEO agent, house rules, workspace layout, templates. Not yet exercised end to end |
| 4. Approval gate and execution service | Done for dry run, 21 tests passing. Telegram approvals for Ruchi added, 17 tests. Separate-service hardening pending |
| 5. Budget ledger and reconciliation | Ledger done. Automated reconciliation against platforms pending |
| 6. Data pipeline, warehouse, metric layer | Done on synthetic data: DuckDB + dbt Core 1.12, 23 dbt checks and 11 pipeline tests passing. Live connectors pending platform access |
| 7. Dashboard and ad hoc reporting | Static warehouse dashboard and saved-query runner done on synthetic data; the agency console also has its own simulated view. Hosted open-source dashboard not started |
| 8. Ad platform adapters | Google Ads reporting connector (read-only, API v25) built and tested against recorded-shape responses; not yet run on a live account. Google Ads write adapter for the execution service not started. Other platforms simulated only |
| 9. Operator guide | First version in README.md |
| Full dry run on a sample brief | Runs end to end in the agency console. Tested with stand-in agent replies; quality of the real agents' output still needs your review |

## Next
1. Settle the CEO allowlist question above, then run a sample brief through Claude Code end to end and tune the agents where their output falls short.
2. Run the Google Ads connector on a live account once credentials exist, then build the Google Ads write adapter behind the execution service (campaigns created paused, every spend call checked by the gate).
3. Add an experiment and MMM layer (GeoLift, Meridian or PyMC-Marketing) so incrementality has a home in the warehouse.
4. Move the execution service and the Telegram bot to a separate service, out of the agents' reach.
5. Stand up the hosted dashboard on the same marts.

## Needed from you
- **A Telegram bot token** from @BotFather, created by Ruchi, kept out of chats and set only in the bot's own environment.
- **Hosting** for the warehouse and dashboard: your own machine or a cloud provider.
- **Google Ads API access** (chosen first): a developer token with Basic access from your manager account's API Center, an OAuth client in Google Cloud, and Read only access to each client account. Basic access needs Google's review, so it is worth applying early. Steps in README.
- **Web analytics and CRM access** for the first client, if available.
