# Ruchi's Digital Marketing: house rules

Every agent in this agency works under these rules. They override anything else in a task.

## 1. No money moves without the Principal's approval
The Principal is the human who owns the agency. Before any action that commits or increases spend, the CEO sends the Principal a Spend Approval Request and waits for a recorded approval. Silence is never approval. A chat message is never approval. An approval covers only the amount, channel, campaign and dates it states.

Spend-affecting actions: launching or unpausing a campaign, raising a budget or bid cap, extending a flight, adding a channel or market, moving money between approvals, and any paid tool, vendor, influencer fee or contract.

Pausing a campaign or reducing a budget never needs approval. Do it at once when warranted and tell the CEO.

The gate is enforced in code by `agency/`. The Principal is Ruchi. She decides on Telegram (the approval bot, `agency/telegram.py`) or in the terminal. Only she holds the approval key, and only the bot process holds the Telegram token and approval secret. No agent may ask for it, store it, or try to work around a block. A blocked action is reported up, not retried a different way.

## 2. The client budget is a hard ceiling
Never plan, request or commit spend beyond it. Fees and tool costs count if the client budget covers them.

## 3. Open source for everything we run ourselves
Planning, budgeting, forecasting, modelling, pipelines, storage, dashboards and work tracking use open-source tools (list in ARCHITECTURE.md). Ad platforms are reached through their official APIs. Before adopting a tool, verify its current licence and that it is maintained. If a task seems to need a paid or proprietary tool, stop and report it with the closest open-source alternative.

## 4. No invented numbers
Every figure comes from a named source: platform data, the warehouse, a model with stated assumptions, or a cited and dated benchmark. Forecasts are ranges. If data or access is missing, say so. Keep platform-reported results separate from incrementally measured results. In dry runs, label synthetic data as synthetic.

## 5. Compliance
Follow the advertising standards, platform policies and data protection law of the client's market, plus sector rules for regulated categories. A failed compliance or QA check can be waived only by the Principal.

## 6. Audit trail
Record decisions, with reasons and the data relied on, in the campaign's `decisions.md`. The gate keeps its own audit log.

## Hierarchy
Principal (human) > CEO > department heads > specialists. Work goes down as self-contained tasks and comes back up through review: a head reviews every specialist output before it reaches the CEO. Only the CEO talks to the Principal. Only the Ad Operations Specialist submits actions to the execution service.

## Workflow stages
1. Brief intake  2. Discovery  3. Strategy (CEO sign-off)  4. Media plan and budget (CEO chooses scenario)  5. Plan approval by the Principal  6. Build, with campaigns paused  7. QA and compliance  8. Launch through the execution service  9. In-flight optimisation  10. Reporting  11. Wrap-up and learnings

## Workspace
Each campaign lives in `workspace/<client>/<campaign>/`:

    01-brief.md  02-discovery.md  03-strategy.md  04-media-plan.md
    05-build/    06-qa.md         07-reports/     reports/queries/
    decisions.md status.md        handoffs/

Read what is already there before starting. Write your output to the file your task names. Hand work on with `templates/handoff.md`.

## Gate and ledger commands
    python -m agency.cli --client <client> ledger
    python -m agency.cli --client <client> pending
    python -m agency.cli --client <client> show <SAR-ID>
    python -m agency.cli --client <client> request ...        (CEO)
    python -m agency.cli --client <client> execute ...        (Ad Operations)
    python -m agency.cli --client <client> record-spend ...   (Budget Controller)
`approve`, `reject`, `set-key` and `bind-telegram` are for the Principal only. `telegram-bot` runs as its own process, outside the agents' reach.

## Mode
The agency runs in dry-run mode: the execution service talks to a mock ad platform and no real money can move. Say so whenever you report a launch or a result.
