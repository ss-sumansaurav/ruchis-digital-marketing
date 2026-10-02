"""Spend Approval Requests to the Principal on Telegram, and her decisions back to the gate.

How it is secured:

* The Principal binds one Telegram account with her approval key
  (`python -m agency.cli --client <c> bind-telegram --user-id N --chat-id N`).
  That prints a secret once; only this bot holds it (env RUCHI_APPROVAL_SECRET).
* A decision is recorded only when it comes from that exact Telegram user id,
  carries the bot's secret, and matches the one-time nonce of the message that
  was sent for that request. Anyone else pressing a button, an old message, or
  a forwarded one is refused and logged.
* From Telegram, MODIFY can only lower the amount or the daily cap. Raising
  either needs a new request or the terminal.
* Silence is never approval: an unanswered request simply stays PENDING.

The bot uses long polling (getUpdates), so it needs no public web address. It
must run as its own process, outside what the agents can read, holding the bot
token and the approval secret. Agents can ask for a request to be sent
(`notify`); they can never decide one.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path

from .core import ApprovalError, Engagement

CHANNEL = "telegram"
API = "https://api.telegram.org/bot{token}/{method}"


class TelegramAPI:
    """Minimal Telegram Bot API client (standard library only)."""

    def __init__(self, token: str):
        self.token = token

    def call(self, method: str, **params) -> dict:
        req = urllib.request.Request(API.format(token=self.token, method=method),
                                     data=json.dumps(params).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=params.get("timeout", 0) + 15) as resp:
            body = json.loads(resp.read())
        if not body.get("ok"):
            raise RuntimeError(f"Telegram {method} failed: {body.get('description')}")
        return body["result"]


class FakeAPI:
    """Stands in for Telegram in dry runs and tests. Records every call."""

    def __init__(self):
        self.calls = []
        self._id = 0

    def call(self, method: str, **params) -> dict:
        self.calls.append((method, params))
        self._id += 1
        return {"message_id": self._id} if method == "sendMessage" else {}


def _inr(v: float, currency: str) -> str:
    sym = "₹" if currency == "INR" else f"{currency} "
    return f"{sym}{v:,.0f}"


def format_request(eng: Engagement, rid: str, detail: dict | None = None, dry_run: bool = True) -> str:
    """One screen, in the order of templates/spend-approval-request.md. `detail` adds the
    planning fields the gate does not hold (objective, KPI, expected range, risks...)."""
    r, cur = eng.data["requests"][rid], eng.data["currency"]
    d = {**r.get("detail", {}), **(detail or {})}
    led = eng.ledger()
    headroom = led["ceiling"] - led["approved"] - r["amount"]
    lines = [
        f"<b>Spend Approval Request {rid}</b>",
        f"{eng.data['client']} · {r['campaign'] if r['campaign'] != '*' else 'all campaigns'} · {r['requested_at'][:10]}",
        "",
        f"<b>Approve:</b> {d.get('what', r['summary'])}",
        f"<b>Amount</b> {_inr(r['amount'], cur)} · <b>channel</b> {r['channel']} · "
        f"<b>dates</b> {r['start']} to {r['end']} · <b>daily cap</b> {_inr(r['daily_cap'], cur)}",
    ]
    for label, key in (("Objective and KPI", "objective"), ("Expected outcome", "expected"),
                       ("Risks and kill criteria", "risks"), ("Alternatives", "alternatives"),
                       ("Checks", "checks")):
        if d.get(key):
            lines.append(f"<b>{label}:</b> {d[key]}")
    lines += [
        f"<b>Budget:</b> ceiling {_inr(led['ceiling'], cur)} · approved {_inr(led['approved'], cur)} · "
        f"spent {_inr(led['spent'], cur)} · headroom after this {_inr(headroom, cur)}",
        "",
        f"To change it, reply: <code>MODIFY {rid} amount daily_cap</code> (lower only)",
        f"To reject with a reason, reply: <code>REJECT {rid} reason</code>",
    ]
    if d.get("link"):
        lines.append(f"Detail: {d['link']}")
    if dry_run:
        lines.append("<i>Dry run: no real money can move.</i>")
    return "\n".join(lines)


class ApprovalBot:
    def __init__(self, state_dir, api, secret: str, dry_run: bool = True):
        self.state_dir, self.api, self.secret, self.dry_run = Path(state_dir), api, secret, dry_run

    def _eng(self, client: str) -> Engagement:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,24}", client):
            raise ApprovalError("bad client name")
        return Engagement(self.state_dir / f"{client}.json")

    # ------------------------------------------------------------- outbound
    def notify(self, client: str, rid: str, detail: dict | None = None) -> dict:
        eng = self._eng(client)
        bound = eng.channel(CHANNEL)
        if not bound:
            raise ApprovalError("no Telegram account bound; the Principal runs bind-telegram first")
        nonce = eng.issue_nonce(rid, CHANNEL)
        keyboard = {"inline_keyboard": [[
            {"text": "APPROVE", "callback_data": f"a:{client}:{rid}:{nonce}"},
            {"text": "REJECT", "callback_data": f"r:{client}:{rid}:{nonce}"},
        ]]}
        assert all(len(b["callback_data"]) <= 64 for b in keyboard["inline_keyboard"][0])
        msg = self.api.call("sendMessage", chat_id=bound["chat_id"], text=format_request(eng, rid, detail, self.dry_run),
                            parse_mode="HTML", reply_markup=keyboard)
        eng._log("telegram-bot", "request_sent", request_id=rid, channel=CHANNEL, message_id=msg.get("message_id"))
        return msg

    # -------------------------------------------------------------- inbound
    def handle(self, update: dict) -> str | None:
        """Process one Telegram update. Returns the reply shown to the user, if any."""
        if "callback_query" in update:
            return self._button(update["callback_query"])
        msg = update.get("message") or {}
        text, user = (msg.get("text") or "").strip(), (msg.get("from") or {}).get("id")
        chat = (msg.get("chat") or {}).get("id")
        if not text or user is None:
            return None
        if text.startswith("/start") or text.startswith("/id"):
            return self._say(chat, f"Your Telegram user id is {user} and this chat id is {chat}. "
                                   f"Give both to bind-telegram to receive approval requests here.")
        m = re.fullmatch(r"(?i)(modify|reject)\s+(?:([A-Za-z0-9_-]+)\s+)?(SAR-\d{4})\s*(.*)", text)
        if not m:
            return None
        verb, client, rid, rest = m.group(1).lower(), m.group(2), m.group(3).upper(), m.group(4)
        try:
            client = client or self._client_for(rid, user)
            eng = self._eng(client)
            nonce = eng.data["requests"].get(rid, {}).get("nonces", {}).get(CHANNEL, "")
            if verb == "reject":
                eng.reject_via(rid, CHANNEL, user, self.secret, nonce, note=rest or "rejected on Telegram")
                return self._say(chat, f"{rid} REJECTED. The agency will not proceed with it.")
            nums = [float(x.replace(",", "")) for x in rest.split()]
            if len(nums) not in (1, 2):
                return self._say(chat, f"Use: MODIFY {rid} amount daily_cap")
            eng.approve_via(rid, CHANNEL, user, self.secret, nonce, amount=nums[0],
                            daily_cap=nums[1] if len(nums) == 2 else None, note="modified on Telegram")
            r = eng.data["requests"][rid]
            return self._say(chat, f"{rid} APPROVED as modified: {_inr(r['approved_amount'], eng.data['currency'])}, "
                                   f"daily cap {_inr(r['daily_cap'], eng.data['currency'])}.")
        except (ApprovalError, FileNotFoundError, ValueError) as e:
            return self._say(chat, f"Not recorded: {e}")

    def _client_for(self, rid: str, user: int) -> str:
        """Find the one engagement bound to this user with this request pending."""
        hits = []
        for path in self.state_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
            except (ValueError, OSError):
                continue
            ch = data.get("channels", {}).get(CHANNEL, {})
            req = data.get("requests", {}).get(rid, {})
            if ch.get("user_id") == user and req.get("status") == "PENDING":
                hits.append(path.stem)
        if len(hits) != 1:
            raise ApprovalError(f"say which client: MODIFY <client> {rid} ..." if hits else f"no pending {rid} for you")
        return hits[0]

    def _button(self, q: dict) -> str:
        user, data = q["from"]["id"], q.get("data", "")
        msg = q.get("message") or {}
        try:
            verb, client, rid, nonce = data.split(":")
            eng = self._eng(client)
            if verb == "a":
                eng.approve_via(rid, CHANNEL, user, self.secret, nonce, note="approved on Telegram")
                result = f"{rid} APPROVED: {_inr(eng.data['requests'][rid]['approved_amount'], eng.data['currency'])}."
            elif verb == "r":
                eng.reject_via(rid, CHANNEL, user, self.secret, nonce, note="rejected on Telegram")
                result = f"{rid} REJECTED."
            else:
                raise ApprovalError("unknown action")
            if msg:
                self.api.call("editMessageReplyMarkup", chat_id=msg["chat"]["id"], message_id=msg["message_id"],
                              reply_markup={"inline_keyboard": []})
                self.api.call("sendMessage", chat_id=msg["chat"]["id"], text=result)
        except (ApprovalError, FileNotFoundError, ValueError) as e:
            result = f"Not recorded: {e}"
        self.api.call("answerCallbackQuery", callback_query_id=q["id"], text=result[:200], show_alert=True)
        return result

    def _say(self, chat, text: str) -> str:
        if chat is not None:
            self.api.call("sendMessage", chat_id=chat, text=text)
        return text

    def send_pending(self) -> list[str]:
        """Send every PENDING request that has no live Telegram message yet.
        This is how requests reach the Principal: agents only create them."""
        sent = []
        for path in sorted(self.state_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text())
            except (ValueError, OSError):
                continue
            if not data.get("channels", {}).get(CHANNEL):
                continue
            for rid, r in data.get("requests", {}).items():
                if r["status"] == "PENDING" and not r.get("nonces", {}).get(CHANNEL):
                    self.notify(path.stem, rid)
                    sent.append(f"{path.stem}/{rid}")
        return sent

    def poll(self, interval: float = 1.0):  # pragma: no cover - needs a live bot
        offset = None
        while True:
            self.send_pending()
            for upd in self.api.call("getUpdates", timeout=20, offset=offset,
                                     allowed_updates=["message", "callback_query"]):
                offset = upd["update_id"] + 1
                self.handle(upd)
            time.sleep(interval)


def from_env(state_dir, dry_run: bool) -> ApprovalBot:
    """The real bot when TELEGRAM_BOT_TOKEN is set (Telegram works the same in dry run:
    only ad spend is simulated). Without a token, a dry run records messages instead."""
    secret = os.environ.get("RUCHI_APPROVAL_SECRET", "")
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if token and secret:
        return ApprovalBot(state_dir, TelegramAPI(token), secret, dry_run=dry_run)
    if dry_run:
        return ApprovalBot(state_dir, FakeAPI(), secret, dry_run=True)
    raise ApprovalError("set TELEGRAM_BOT_TOKEN and RUCHI_APPROVAL_SECRET in the bot's own environment")
