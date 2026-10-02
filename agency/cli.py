"""Command line for the approval gate and ledger.

  python -m agency.cli --client acme init --ceiling 500000 --currency INR
  python -m agency.cli --client acme set-key            (Principal only)
  python -m agency.cli --client acme request --campaign "*" --channel paid_search \
        --amount 200000 --start 2026-11-01 --end 2026-11-30 --daily-cap 8000 --summary "..."
  python -m agency.cli --client acme pending | show SAR-0001 | ledger
  python -m agency.cli --client acme approve SAR-0001 [--amount N] [--daily-cap N]   (Principal only)
  python -m agency.cli --client acme reject SAR-0001 --note "..."                    (Principal only)
  python -m agency.cli --client acme execute --type launch --request SAR-0001 ...
  python -m agency.cli --client acme bind-telegram --user-id N --chat-id N          (Principal only)
  python -m agency.cli --client acme telegram-bot                                    (approval bot process)
"""
import argparse
import getpass
import json
import sys
from pathlib import Path

from .core import ApprovalError, Engagement, MockAdapter, SpendBlocked


def _mode() -> str:
    cfg = Path(__file__).resolve().parent.parent / "config" / "agency.yaml"
    for line in cfg.read_text().splitlines():
        if line.startswith("mode:"):
            return line.split(":", 1)[1].split("#")[0].strip()
    return "dry_run"


def main(argv=None):
    p = argparse.ArgumentParser(prog="agency")
    p.add_argument("--client", required=True)
    p.add_argument("--state-dir", default="state")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init"); s.add_argument("--ceiling", type=float, required=True); s.add_argument("--currency", required=True)
    sub.add_parser("set-key")
    s = sub.add_parser("request")
    for flag in ("--campaign", "--channel", "--start", "--end", "--summary"):
        s.add_argument(flag, required=True)
    s.add_argument("--amount", type=float, required=True); s.add_argument("--daily-cap", type=float, required=True)
    s.add_argument("--by", default="ceo")
    s.add_argument("--detail-file", type=Path, help="JSON with what/objective/expected/risks/alternatives/checks/link")
    sub.add_parser("pending"); sub.add_parser("ledger")
    s = sub.add_parser("show"); s.add_argument("id")
    s = sub.add_parser("approve"); s.add_argument("id"); s.add_argument("--amount", type=float); s.add_argument("--daily-cap", type=float); s.add_argument("--note", default="")
    s = sub.add_parser("reject"); s.add_argument("id"); s.add_argument("--note", default="")
    s = sub.add_parser("execute")
    s.add_argument("--type", required=True); s.add_argument("--campaign", required=True)
    s.add_argument("--request"); s.add_argument("--channel"); s.add_argument("--budget", type=float)
    s.add_argument("--daily-budget", type=float); s.add_argument("--start"); s.add_argument("--end")
    s = sub.add_parser("bind-telegram"); s.add_argument("--user-id", type=int, required=True); s.add_argument("--chat-id", type=int, required=True)
    s = sub.add_parser("telegram-bot"); s.add_argument("--once", action="store_true", help="send pending requests and exit")
    s = sub.add_parser("record-spend"); s.add_argument("--campaign", required=True); s.add_argument("--amount", type=float, required=True); s.add_argument("--date", required=True)

    a = p.parse_args(argv)
    path = Path(a.state_dir) / f"{a.client}.json"
    out = lambda obj: print(json.dumps(obj, indent=2))
    try:
        if a.cmd == "init":
            Engagement.create(path, a.client, a.currency, a.ceiling)
            return print(f"created {path}")
        eng = Engagement(path)
        if a.cmd == "set-key":
            old = getpass.getpass("Current key: ") if eng.data["key"] else None
            new = getpass.getpass("New Principal key: ")
            if new != getpass.getpass("Repeat: "):
                sys.exit("keys do not match")
            eng.set_key(new, old); print("key set")
        elif a.cmd == "request":
            print(eng.create_request(campaign=a.campaign, channel=a.channel, amount=a.amount, start=a.start,
                                     end=a.end, daily_cap=a.daily_cap, summary=a.summary, requested_by=a.by,
                                     detail=json.loads(a.detail_file.read_text()) if a.detail_file else None))
        elif a.cmd == "pending":
            out([r for r in eng.data["requests"].values() if r["status"] == "PENDING"])
        elif a.cmd == "show":
            out(eng.data["requests"].get(a.id) or {"error": "no such request"})
        elif a.cmd == "ledger":
            out(eng.ledger())
        elif a.cmd == "approve":
            eng.approve(a.id, getpass.getpass("Principal key: "), amount=a.amount, daily_cap=a.daily_cap, note=a.note)
            print(f"{a.id} APPROVED")
        elif a.cmd == "reject":
            eng.reject(a.id, getpass.getpass("Principal key: "), note=a.note); print(f"{a.id} REJECTED")
        elif a.cmd == "execute":
            action = {"type": a.type, "campaign": a.campaign, "request_id": a.request, "channel": a.channel,
                      "budget": a.budget, "daily_budget": a.daily_budget, "start": a.start, "end": a.end}
            action = {k: v for k, v in action.items() if v is not None}
            # Dry run only: live platform adapters are not built yet.
            out(eng.execute(action, MockAdapter()))
        elif a.cmd == "bind-telegram":
            secret = eng.bind_channel(getpass.getpass("Principal key: "), "telegram", a.user_id, a.chat_id)
            print("Telegram bound. Put this secret in the approval bot's environment as RUCHI_APPROVAL_SECRET.")
            print("It is shown once and must never be given to an agent:")
            print(secret)
        elif a.cmd == "telegram-bot":
            import os
            from .telegram import from_env
            if not a.once and not os.environ.get("TELEGRAM_BOT_TOKEN"):
                sys.exit("TELEGRAM_BOT_TOKEN is not loaded in this terminal window. Run "
                         "`read -rs TELEGRAM_BOT_TOKEN && export TELEGRAM_BOT_TOKEN`, paste the token, press Enter, "
                         "then start the bot again in the same window.")
            bot = from_env(a.state_dir, dry_run=_mode() != "live")
            if a.once:
                out(bot.send_pending())
            else:
                bot.poll()
        elif a.cmd == "record-spend":
            eng.record_spend(a.campaign, a.amount, a.date); print("recorded")
    except SpendBlocked as e:
        sys.exit(f"BLOCKED: {e}")
    except (ApprovalError, FileNotFoundError) as e:
        sys.exit(f"ERROR: {e}")


if __name__ == "__main__":
    main()
