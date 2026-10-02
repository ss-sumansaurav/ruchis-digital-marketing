# Ruchi's Digital Marketing

An AI-run digital marketing agency: 34 agents in a three-tier hierarchy, a code-enforced spend approval gate, and a budget ledger. Built from `BUILD_PROMPT.md`.

**Status: working in dry run.** No real money can move. There are two ways to run the agency:

1. **The agency console** (`app/agency-console.html`, also published as a Claude artifact). You give it a brief and a budget; the agents run on Claude, the CEO raises spend requests, you approve or reject each one with a button, and approved campaigns launch on a simulated ad platform with a live dashboard and ad hoc reports. All performance figures in it are simulated.
2. **The Claude Code setup** in this folder (agents as subagents plus the Python approval gate), described below.

Connections to real ad platforms and the hosted open-source data stack are not built yet. See ARCHITECTURE.md.

## What is in this folder

| Path | What it is |
|---|---|
| `app/agency-console.html` | The agency console: runs the whole workflow in dry run inside Claude |
| `.claude/agents/` | The agents: `ceo.md`, 7 department heads, 26 specialists |
| `CLAUDE.md` | House rules every agent works under |
| `agency/` | Approval gate, budget ledger, execution service (Python, no dependencies) |
| `tests/` | 21 tests proving unapproved or out-of-scope spend is blocked |
| `templates/` | Client brief, Spend Approval Request, handoff |
| `config/agency.yaml` | Setup values, including the ones still to confirm |
| `ARCHITECTURE.md` | Design, build status, what is needed from you |
| `BUILD_PROMPT.md` | The original specification |

## Running it

The agents are written as Claude Code project subagents. Open this folder in Claude Code; `.claude/settings.json` makes the main session the CEO agent, which delegates to the heads, who delegate to their specialists.

Check the gate works on your machine first (Python 3.10 or later):

    python -m unittest discover -s tests -v

## Operating it

**1. Set up a client** (once per client budget):

    python -m agency.cli --client acme init --ceiling 500000 --currency INR
    python -m agency.cli --client acme set-key

`set-key` asks you to choose an approval key. Only you should know it. Never type it into a chat with an agent.

**2. Give the CEO a brief.** In Claude Code, paste the client's brief and budget. The CEO runs intake, strategy and planning, and reports to you at each stage.

**3. Approve or reject spend.** The CEO shows you a Spend Approval Request with an ID. In a separate terminal:

    python -m agency.cli --client acme approve SAR-0001
    python -m agency.cli --client acme approve SAR-0001 --amount 150000 --daily-cap 6000    # modify
    python -m agency.cli --client acme reject  SAR-0001 --note "reason"

**4. Check the budget position at any time:**

    python -m agency.cli --client acme ledger

**5. Ask for a report.** Ask the CEO in plain language. (Until the data pipeline is built, reports can only use files you provide.)

**6. Stop everything.** Tell the CEO to stop. Pauses never need approval.
