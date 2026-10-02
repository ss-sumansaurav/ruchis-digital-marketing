# Architecture and build status

## Runtime
**Recommendation: Claude Code, with the agents as project subagents.** Each agent is a Markdown file with a short YAML header (name, description, allowed tools) and its instructions as the body. Reasons:

- The files are plain text, so you can read and edit every agent, and they can be moved to another agent framework later.
- The CEO runs as the main session and is the only agent that talks to you. Subagents cannot ask the user questions, which enforces "only the CEO talks to the Principal".
- The CEO's tool list allows it to delegate only to the seven department heads (plus the ad hoc reporting analyst). Heads delegate to specialists. Claude Code's documentation states that subagents can spawn their own subagents up to three layers below the main session by default in current versions; this design uses two.
- Each agent gets only the tools it needs. The compliance and QA reviewers cannot write files.

Reference: https://code.claude.com/docs/en/sub-agents

This has not yet been run inside Claude Code. The agent files were checked for valid headers and unique names; the first real test is the dry run described under "Next".

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

**Limit you should know about.** In this dry-run setup the gate's state file sits on the same machine as the agents. The key stops an agent recording an approval through the gate, but it does not stop a process with file access from tampering with the state file directly. Before live use, the execution service must run as a separate service that alone holds the ad platform write credentials and its own state, out of the agents' reach. Agents then have no route to a platform except through it.

## Data and reporting (planned, not built)

    ad platforms, web analytics, CRM
        -> ingestion (dlt or Meltano), read-only credentials
        -> warehouse (PostgreSQL, DuckDB or ClickHouse)
        -> metric definitions (dbt Core)
        -> dashboard (Apache Superset, Metabase open-source edition, or Grafana)
        -> ad hoc reports (SQL on the marts, saved queries)

Dashboard views: executive overview (budget, pacing, KPIs against target, forecast), channel and campaign performance, funnel, approvals, alerts. Every tile shows a data-as-of time, because ad platform reporting lags.

Other open-source candidates: Robyn, Meridian, PyMC-Marketing (media mix modelling); Prophet, statsmodels, SciPy, OR-Tools (forecasting, optimisation); GeoLift, CausalImpact, GrowthBook (experiments); ChannelAttribution; Matomo, PostHog, Plausible (analytics); Mautic, listmonk (email); Lighthouse (site audits); Penpot, Inkscape, GIMP, FFmpeg (creative); Airflow, Dagster, Prefect (scheduling). Licences and maintenance status were not re-verified during this build; the agents are instructed to verify before adopting each one.

## Build status

| Step in BUILD_PROMPT.md | Status |
|---|---|
| 1. Architecture note | Done (this file) |
| 2. Agent definitions | Done: 34 agents. Not yet run in Claude Code |
| 3. Orchestration, shared workspace, logging | Partly: CEO agent, house rules, workspace layout, templates. Not yet exercised end to end |
| 4. Approval gate and execution service | Done for dry run, 21 tests passing. Separate-service hardening pending |
| 5. Budget ledger and reconciliation | Ledger done. Automated reconciliation against platforms pending |
| 6. Data pipeline, warehouse, metric layer | Not started (needs hosting and platform access) |
| 7. Dashboard and ad hoc reporting | Done in the agency console, on simulated data. The hosted open-source dashboard is not started |
| 8. Ad platform adapters | Simulated platform only |
| 9. Operator guide | First version in README.md |
| Full dry run on a sample brief | Runs end to end in the agency console. Tested with stand-in agent replies; quality of the real agents' output still needs your review |

## Next
1. Run real briefs through the agency console and tune the agents where their output falls short.
2. Build the data pipeline, warehouse and dashboard on synthetic data.
3. Build the first live adapter, in read-only mode first.
4. Move the execution service to a separate service and add approval through your preferred channel.

## Needed from you
- **Principal's name**, for `config/agency.yaml`.
- **Currency and market.** INR and India are assumed.
- **Where approval requests should reach you** after the terminal phase: chat, email, Slack or other.
- **Hosting** for the warehouse and dashboard: your own machine or a cloud provider.
- **Which ad platforms come first**, and API access to them: developer credentials, and account access from each client. Platform API approval can take time, so it is worth starting early.
- **Web analytics and CRM access** for the first client, if available.
