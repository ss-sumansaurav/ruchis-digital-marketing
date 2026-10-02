# Ruchi's Digital Marketing

An AI-run digital marketing agency: 34 agents in a three-tier hierarchy, a code-enforced spend approval gate, and a budget ledger. Built from `BUILD_PROMPT.md`.

**Status: working in dry run.** No real money can move. There are two ways to run the agency:

1. **The agency console** (`app/agency-console.html`, also published as a Claude artifact). You give it a brief and a budget; the agents run on Claude, the CEO raises spend requests, you approve or reject each one with a button, and approved campaigns launch on a simulated ad platform with a live dashboard and ad hoc reports. All performance figures in it are simulated.
2. **The Claude Code setup** in this folder (agents as subagents plus the Python approval gate), described below.

The data pipeline (DuckDB warehouse, dbt Core metric layer, dashboard and ad hoc reports) is built and tested on synthetic data. Connections to real ad platforms are not built yet. See ARCHITECTURE.md.

## What is in this folder

| Path | What it is |
|---|---|
| `app/agency-console.html` | The agency console: runs the whole workflow in dry run inside Claude |
| `.claude/agents/` | The agents: `ceo.md`, 7 department heads, 26 specialists |
| `CLAUDE.md` | House rules every agent works under |
| `agency/` | Approval gate, budget ledger, execution service, Telegram approval bot (Python, no dependencies) |
| `pipeline/` | Ingestion, synthetic data, dashboard and ad hoc report runner |
| `warehouse/` | dbt Core project: staging, core fact table, marts, metric definitions |
| `reports/queries/` | Saved ad hoc queries |
| `tests/` | 21 gate tests (unapproved or out-of-scope spend is blocked), 17 Telegram approval tests, 11 pipeline tests and 9 Google Ads connector tests |
| `templates/` | Client brief, Spend Approval Request, handoff |
| `config/agency.yaml` | Setup values, including the ones still to confirm |
| `ARCHITECTURE.md` | Design, build status, what is needed from you |
| `BUILD_PROMPT.md` | The original specification |

## Running it

The agents are written as Claude Code project subagents. Open this folder in Claude Code; `.claude/settings.json` makes the main session the CEO agent, which delegates to the heads, who delegate to their specialists.

Check the gate works on your machine first (Python 3.10 or later):

    python -m unittest discover -s tests -v

The pipeline tests need `pip install -r requirements.txt` (duckdb, dbt-duckdb) and are skipped without it.

See the pipeline on synthetic data:

    python -m pipeline.run --client demo --synthetic
    open workspace/demo/dashboard.html
    python -m pipeline.adhoc --client demo platform_vs_backend_gap

## Operating it

**1. Set up a client** (once per client budget):

    python -m agency.cli --client acme init --ceiling 500000 --currency INR
    python -m agency.cli --client acme set-key

`set-key` asks you to choose an approval key. Only you should know it. Never type it into a chat with an agent.

**2. Give the CEO a brief.** In Claude Code, paste the client's brief and budget. The CEO runs intake, strategy and planning, and reports to you at each stage.

**3. Set up Telegram approvals** (once). Requests go to Suman's Telegram account; binding it needs the Principal's approval key:

1. In Telegram, open @BotFather, send `/newbot` and keep the token it gives you.
2. Start the bot in its own terminal, outside the agents' folder access: `TELEGRAM_BOT_TOKEN=<token> python -m agency.cli --client acme telegram-bot`. From Suman's Telegram, send it `/start`; it replies with the user id and chat id.
3. Bind your account with your approval key: `python -m agency.cli --client acme bind-telegram --user-id <id> --chat-id <id>`. It prints a secret once.
4. Restart the bot with both values: `TELEGRAM_BOT_TOKEN=<token> RUCHI_APPROVAL_SECRET=<secret> python -m agency.cli --client acme telegram-bot`.

From then on, every Spend Approval Request arrives on Telegram as one screen with APPROVE and REJECT buttons. Reply `MODIFY SAR-0001 150000 6000` to approve a lower amount or daily cap, or `REJECT SAR-0001 reason`. Only your Telegram account can decide; anyone else's taps are refused and logged. From Telegram you can only lower a request, never raise it. Never share the token, the secret or your key with an agent.

**4. Approve or reject spend in the terminal** (always available, and the only way to approve more than was requested):

    python -m agency.cli --client acme approve SAR-0001
    python -m agency.cli --client acme approve SAR-0001 --amount 150000 --daily-cap 6000    # modify
    python -m agency.cli --client acme reject  SAR-0001 --note "reason"

**5. Check the budget position at any time:**

    python -m agency.cli --client acme ledger

**6. Connect Google Ads (read-only reporting).** One-time setup, all done in your own Google accounts:

1. In a Google Ads manager account, open Admin > API Center and request a developer token. It starts at test access, which only works on test accounts; apply for Basic access, which Google reviews.
2. In Google Cloud, create a project, enable the Google Ads API, and create an OAuth client (Desktop app).
3. Give a Google user **Read only** access to each client's Google Ads account (or link the accounts to your manager account), then create a refresh token signed in as that user.
4. Set `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_CLIENT_ID`, `GOOGLE_ADS_CLIENT_SECRET`, `GOOGLE_ADS_REFRESH_TOKEN` (and `GOOGLE_ADS_LOGIN_CUSTOMER_ID` for a manager account) in the environment that runs the pipeline. Never paste them into a chat.

Then pull the last 30 days and rebuild the warehouse:

    python -m pipeline.connectors.google_ads --client acme --customer-id 123-456-7890 \
        --campaign-map workspace/acme/google-ads-campaigns.json --out state/pipeline/acme/extracts
    python -m pipeline.run --client acme --extracts state/pipeline/acme/extracts

The campaign map is a JSON object from Google Ads campaign id to the campaign name used in the approval gate. Any campaign spending without an approval behind it shows up as an `unapproved_spend` alert. The connector only reads; launching and budget changes on Google Ads are not built yet and will go only through the approval gate.

**7. Ask for a report.** Ask the CEO in plain language; the Ad Hoc Reporting Analyst answers from the warehouse with a saved, rerunnable query. Until a live connector exists, the warehouse holds only synthetic data or extracts you provide.

**8. Stop everything.** Tell the CEO to stop. Pauses never need approval.
