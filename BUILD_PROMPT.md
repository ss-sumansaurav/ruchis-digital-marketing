# Build prompt: an AI-run digital marketing agency

## 1. What you are building and why

I run a digital marketing company. Build me a multi-agent system that operates as a full-service digital media agency. When a client gives me a brief and a fixed budget, the system must be able to plan, build, launch, optimise, measure and report on the work end to end, with me personally approving every commitment of money.

The benchmark is the top tier of the global agency networks: OMD and the wider Omnicom media group, WPP Media, Publicis Media, dentsu. Model the org structure, craft standards and working rhythm on how the strongest teams at those agencies operate: strategy grounded in audience evidence, plans that tie every unit of budget to a measurable outcome, strict QA before anything goes live, and honest measurement. Each agent should work at the level of a senior practitioner in its own discipline, not as a generalist.

## 2. Setup values

Use these throughout. Ask me for any that are still blank.

- Agency name: [AGENCY NAME]
- Human principal and sole spend approver: [MY NAME] (referred to below as "the Principal")
- Default currency and market: [CURRENCY], [MARKET]
- Agent framework / runtime to build on: [FRAMEWORK, or "recommend one"]
- Where approval requests reach me: [CHAT / EMAIL / SLACK / OTHER]
- Hosting for the data stack and dashboard: [LOCAL / CLOUD PROVIDER]

## 3. Rules that override everything else

**3.1 No money moves without my approval.** Before any action that commits or increases spend, the system sends me a Spend Approval Request (format in section 7) and waits for an explicit APPROVE, REJECT or MODIFY. Silence is never approval. An approval covers only the amount, channel, campaign and dates stated in it.

Spend-affecting actions include: launching or unpausing a campaign, raising a budget or bid cap, extending a flight, adding a channel or market, moving money between line items, and any paid tool, vendor, influencer fee or contract.

I may approve an envelope (for example, a channel budget for a period with a daily cap and a reallocation tolerance). Optimisation inside an approved envelope does not need a new request. Anything outside it does. The default tolerance is zero until I set one.

Pausing a campaign or reducing spend never needs approval, because it is the safe direction. Do it immediately when warranted and notify me.

Enforce this gate in code, not only in agent instructions. The only component holding write-capable ad platform credentials is an execution service that refuses any spend-affecting call lacking a valid, unexpired approval record matching amount, channel, campaign and dates. No agent can bypass it. All campaigns are created in a paused state.

**3.2 The client budget is a hard ceiling.** A budget ledger tracks approved, committed, spent and remaining amounts, including agency fees and tool costs if the client budget covers them. The system must never plan or request spend that would exceed the ceiling.

**3.3 Open source for everything we run ourselves.** Planning, budgeting, forecasting, modelling, data pipelines, storage, dashboards and work tracking all use open-source tools (section 8). The ad platforms themselves (Google Ads, Meta, DV360, Amazon Ads, LinkedIn and so on) are proprietary and unavoidable; connect to them through their official APIs. If a task appears to need any other paid or proprietary tool, stop and tell me, with the closest open-source alternative.

**3.4 No invented numbers.** Every figure in a plan, report or approval request comes from a named source: platform data, the warehouse, a model with stated assumptions, or a cited benchmark. Forecasts are given as ranges with assumptions. If data is missing or access is not set up, say so plainly instead of estimating silently. Distinguish platform-reported results from incrementally measured results.

**3.5 Compliance.** All work follows the advertising standards, platform policies and data protection law of the client's market (for example ASCI and the DPDP Act in India, GDPR in the EU, FTC rules in the US), plus any sector rules for regulated categories such as finance, health or alcohol.

**3.6 Audit trail.** Every decision, handoff, approval request, approval and platform change is logged with timestamp, agent, rationale and the data it relied on.

## 4. Organisation

Build the agents in this hierarchy. Specialists report to their department head; heads report to the CEO; the CEO reports to me.

**Tier 0: the Principal (human).** Approves or rejects all spend. Can override anything.

**Tier 1: CEO Agent.** Makes the final call inside the agent organisation. Accepts or declines a brief, sets the team for it, resolves disagreements between department heads, signs off the strategy, the media plan and every Spend Approval Request before it reaches me, and owns client outcomes. The CEO cannot approve spend. The CEO is my main point of contact and gives me a short status summary at each stage.

**Tier 2 and 3: departments.**

| Department head | Mandate | Specialists reporting in |
|---|---|---|
| Client Services Director | Brief intake, scope, timelines, client communication, status reports | Account Manager; Project/Traffic Manager |
| Chief Strategy Officer | Business problem, audience, positioning, communications strategy, KPI framework | Audience and Insights Analyst; Competitive and Category Analyst |
| Head of Media Planning and Investment | Channel mix, budget allocation, flighting, forecasts, scenario plans | Media Planner; Budget and Forecasting Analyst (media mix modelling, response curves, optimisation) |
| Head of Performance and Activation | Campaign build, launch readiness, in-flight optimisation | Paid Search; Paid Social; Programmatic, Display and Video; Marketplace and Retail Media; SEO; Email, CRM and Lifecycle; Influencer and Affiliate; Ad Operations (trafficking, tagging, pixels, feeds, UTMs) |
| Head of Creative and Content | Messaging, creative concepts, asset production, landing experience | Copywriter; Designer; Video and Motion; Landing Page and CRO Specialist |
| Head of Marketing Science | Measurement design, data, dashboard, reporting, experiments, attribution | Data Engineer; Performance Analyst; Attribution and Incrementality Analyst; Dashboard Developer; Ad Hoc Reporting Analyst |
| Head of Finance and Governance | Budget ledger, reconciliation of platform spend against approvals, compliance, brand safety | Budget Controller; Compliance and Brand Safety Reviewer; independent QA Reviewer |

Only activate the specialists a given brief needs. A search-only brief should not wake the influencer team.

## 5. What every agent definition must contain

Write each agent as its own definition file with:

1. **Role and mandate**, and who it reports to.
2. **Inputs it expects and outputs it produces**, with a template for each output (for example: strategy brief, media plan, flighting calendar, campaign build sheet, tracking plan, QA checklist, weekly report).
3. **Decision rights:** what it decides alone, what needs its head, what needs the CEO, what needs me.
4. **Craft playbook:** the methods a senior person in that role actually uses. Examples: the Media Planner works from reach and frequency goals, response curves and diminishing returns; the Paid Search Specialist works from account structure, match types, negatives, bidding strategy and search term reviews; the Attribution Analyst knows when to use media mix modelling, geo experiments or path-based attribution and the limits of each. Go to this level of depth for every role.
5. **Tools it may use**, on a least-privilege basis. Read access is broad; write access is narrow.
6. **Quality checklist** it runs before handing work on.
7. **Escalation triggers:** the conditions under which it stops and raises the issue upward.
8. **Handoff format,** so the next agent can act without asking for the context again.

Every department head reviews specialist output before it moves up. The QA Reviewer checks launch readiness independently of the team that built the campaign.

All agents work from one shared campaign workspace holding the brief, strategy, plan, budget ledger, decision log and approval log, so that handoffs happen through structured records rather than retelling.

## 6. Operating workflow

1. **Brief intake.** Client Services captures objective, budget, dates, market, audience, KPIs, brand and legal constraints, and what access exists (ad accounts, analytics, CRM, past data). Missing essentials are listed as questions for me.
2. **Discovery.** Audit of past performance, accounts, tracking, site and competitors.
3. **Strategy.** Audience, proposition, channel roles, KPI tree and measurement plan. CEO signs off.
4. **Media plan and budget.** Channel mix, allocation, flighting, forecast ranges and at least two alternative scenarios (for example, efficiency-led and growth-led) with the trade-offs explained. CEO chooses one and says why.
5. **Plan approval.** The plan comes to me as a Spend Approval Request. Nothing is built for launch until I approve or modify it.
6. **Build.** Creative, landing pages, tracking and campaigns are built, with campaigns paused.
7. **QA.** Tracking fires correctly, links and UTMs work, budgets and caps match the approval, targeting and exclusions are right, creative passes compliance and platform policy.
8. **Launch.** The execution service launches only what the approval record covers.
9. **In-flight optimisation.** Daily pacing and anomaly checks, weekly optimisation reviews. Changes inside an approved envelope proceed and are logged; changes outside it come to me.
10. **Reporting.** Dashboard always on, weekly summary, ad hoc reports on request.
11. **Wrap-up.** Results against KPIs, what worked, what did not, spend reconciliation, and learnings saved for future briefs.

## 7. Spend Approval Request format

Every request to me contains, in this order:

- Request ID, client, campaign, date
- What I am being asked to approve, in one sentence
- Amount, channel, dates, daily cap, and any reallocation tolerance requested
- Objective and the KPI it serves
- Expected outcome as a range, with the assumptions and data source behind it
- Budget position: client ceiling, already approved, spent to date, remaining after this request
- Main risks and the kill criteria (the conditions under which the campaign will be paused automatically)
- Alternatives considered and why the CEO recommends this one
- Options: APPROVE / REJECT / MODIFY

Keep it to one screen. Link to detail instead of pasting it.

## 8. Open-source tooling

Use these as starting candidates. Before adopting any tool, verify its current licence and that it is actively maintained, and tell me if either has changed.

| Purpose | Candidates |
|---|---|
| Media mix modelling and budget optimisation | Robyn, Meridian, PyMC-Marketing |
| Forecasting and scenario planning | Prophet, statsmodels, SciPy, OR-Tools |
| Incrementality and experiments | GeoLift, CausalImpact, GrowthBook |
| Attribution | ChannelAttribution (Markov and heuristic models) |
| Data ingestion from ad platforms | dlt, Meltano |
| Storage | PostgreSQL, DuckDB, ClickHouse |
| Transformation and metric definitions | dbt Core |
| Orchestration and scheduling | Apache Airflow, Dagster, Prefect |
| Dashboard | Apache Superset, Metabase (open-source edition), Grafana |
| Web and product analytics, tag management | Matomo, PostHog, Plausible |
| Email, CRM and marketing automation | Mautic, listmonk |
| SEO and site audits | Lighthouse |
| Creative production | Penpot, Inkscape, GIMP, FFmpeg |
| Planning sheets and work tracking | Grist, LibreOffice, OpenProject, Plane |

## 9. Measurement, dashboard and reporting

**Data foundation.** Ingest spend and performance data from every active ad platform, plus web analytics and conversion or CRM data where available, into one warehouse. Define every metric once in the transformation layer so that all reports agree.

**Live dashboard.** Build these views:

- Executive overview: budget approved, spent and remaining; pacing against plan; KPIs against target; forecast to end of flight
- Channel and campaign performance, down to ad group and creative
- Funnel: impressions, clicks, sessions, conversions, revenue, with CPM, CTR, CPC, CVR, CPA, ROAS and CAC
- Approvals: every request, its status, and spend against each approval
- Alerts: overspend risk, pacing deviation, sudden cost or conversion changes, broken tracking

"Real time" means as fresh as each source allows. Ad platform reporting lags and conversions are restated after the fact, so refresh each source at the fastest sensible cadence and show a "data as of" timestamp on every tile. Never present delayed data as live.

**Ad hoc reports.** The Ad Hoc Reporting Analyst takes a plain-language question from me or a client-facing agent, queries the warehouse, and returns the answer with the numbers, a chart where useful, the metric definitions, period, source and caveats. Reports can be exported as PDF, spreadsheet or slides. Save the query so the report can be rerun.

**Scheduled reports.** A weekly performance summary and an end-of-campaign report, each stating what happened, why, and what the team will do next.

## 10. Build order and deliverables

1. Architecture note: framework, how agents are orchestrated, repo layout, data flow, where the approval gate sits.
2. Agent definition files for every role in section 4, to the standard in section 5.
3. Orchestration: the CEO agent, delegation, shared workspace, logging.
4. Approval gate and execution service, with tests proving that an unapproved or out-of-scope spend call is blocked.
5. Budget ledger and reconciliation.
6. Data pipeline, warehouse, metric layer.
7. Dashboard and ad hoc reporting.
8. Ad platform adapters, each with a mock version for dry runs.
9. Operator guide: how I submit a brief, approve spend, ask for a report, and stop everything.

The system has two modes. Dry run is the default: mock adapters, synthetic data clearly labelled as synthetic, no real spend possible. Live mode requires real credentials and still passes every spend through the approval gate.

Finish by running a complete dry run on a sample brief and showing me the strategy, the media plan, a Spend Approval Request, the blocked-spend test, and the populated dashboard.

## 11. How to start

Before writing any code, reply with: the framework you recommend and why, the architecture, the repo layout, the access and credentials you will need from me, and any open questions. Wait for my go-ahead before building.
