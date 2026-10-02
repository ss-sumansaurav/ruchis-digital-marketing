"""Spend approval gate, budget ledger and execution service.

One Engagement = one client budget. Rules enforced here, in code:

* No spend-increasing action runs without an APPROVED request that matches
  its channel, campaign, dates, amount and daily cap.
* Approvals and rejections need the Principal's key. Only a salted hash of
  the key is stored, so an agent cannot record an approval.
* Total approved spend can never exceed the client ceiling.
* Pausing and decreasing budgets are always allowed.
* Unknown action types are refused (default deny).
* Every event is appended to an audit log.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import date, datetime, timezone
from pathlib import Path

SPEND_ACTIONS = {"launch", "increase_budget", "extend_flight"}
SAFE_ACTIONS = {"pause", "decrease_budget"}


class SpendBlocked(Exception):
    """The execution service refused a spend-affecting action."""


class ApprovalError(Exception):
    """An approval, rejection or request could not be recorded."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash(key: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", key.encode(), bytes.fromhex(salt), 200_000).hex()


def _d(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def _money(value) -> float:
    return round(float(value), 2)


class MockAdapter:
    """Stands in for an ad platform in dry runs. Records what it was asked to do."""

    def __init__(self):
        self.calls = []

    def apply(self, action: dict) -> dict:
        self.calls.append(dict(action))
        return {"ok": True, "dry_run": True}


class Engagement:
    def __init__(self, path):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text())

    # ------------------------------------------------------------ setup
    @classmethod
    def create(cls, path, client: str, currency: str, ceiling: float) -> "Engagement":
        path = Path(path)
        if path.exists():
            raise ApprovalError(f"{path} already exists")
        if ceiling <= 0:
            raise ApprovalError("budget ceiling must be positive")
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"client": client, "currency": currency, "ceiling": _money(ceiling),
                "key": None, "seq": 0, "requests": {}, "campaigns": {}, "spend": []}
        path.write_text(json.dumps(data, indent=2))
        eng = cls(path)
        eng._log("system", "engagement_created", ceiling=data["ceiling"], currency=currency)
        return eng

    def _save(self):
        self.path.write_text(json.dumps(self.data, indent=2))

    def _log(self, actor: str, event: str, **detail):
        line = {"at": _now(), "actor": actor, "event": event, **detail}
        with open(self.path.with_suffix(".audit.jsonl"), "a") as f:
            f.write(json.dumps(line) + "\n")

    def set_key(self, new_key: str, old_key: str | None = None):
        if self.data["key"] and not self._key_ok(old_key or ""):
            raise ApprovalError("current key required to change the key")
        if len(new_key) < 8:
            raise ApprovalError("key must be at least 8 characters")
        salt = secrets.token_hex(16)
        self.data["key"] = {"salt": salt, "hash": _hash(new_key, salt)}
        self._save()
        self._log("principal", "key_set")

    def _key_ok(self, key: str) -> bool:
        k = self.data["key"]
        return bool(k) and hmac.compare_digest(_hash(key, k["salt"]), k["hash"])

    # --------------------------------------------------------- requests
    def approved_total(self) -> float:
        return _money(sum(r["approved_amount"] for r in self.data["requests"].values()
                          if r["status"] == "APPROVED"))

    def create_request(self, *, campaign: str, channel: str, amount: float, start, end,
                       daily_cap: float, summary: str, requested_by: str = "ceo") -> str:
        amount, daily_cap = _money(amount), _money(daily_cap)
        if amount <= 0 or daily_cap <= 0:
            raise ApprovalError("amount and daily cap must be positive")
        if _d(start) > _d(end):
            raise ApprovalError("start date is after end date")
        if self.approved_total() + amount > self.data["ceiling"]:
            raise ApprovalError(
                f"request of {amount} would exceed the client ceiling "
                f"({self.data['ceiling']} ceiling, {self.approved_total()} already approved)")
        self.data["seq"] += 1
        rid = f"SAR-{self.data['seq']:04d}"
        self.data["requests"][rid] = {
            "id": rid, "campaign": campaign, "channel": channel, "amount": amount,
            "start": str(_d(start)), "end": str(_d(end)), "daily_cap": daily_cap,
            "summary": summary, "requested_by": requested_by, "requested_at": _now(),
            "status": "PENDING", "approved_amount": 0.0, "decided_at": None, "note": ""}
        self._save()
        self._log(requested_by, "request_created", request_id=rid, amount=amount,
                  channel=channel, campaign=campaign)
        return rid

    def _decide(self, rid: str, key: str) -> dict:
        if not self.data["key"]:
            raise ApprovalError("no Principal key set; run set-key first")
        if not self._key_ok(key):
            self._log("unknown", "decision_refused_bad_key", request_id=rid)
            raise ApprovalError("wrong Principal key")
        req = self.data["requests"].get(rid)
        if not req:
            raise ApprovalError(f"no such request {rid}")
        if req["status"] != "PENDING":
            raise ApprovalError(f"{rid} is already {req['status']}")
        return req

    def approve(self, rid: str, key: str, *, amount: float | None = None,
                daily_cap: float | None = None, note: str = ""):
        """Approve as requested, or MODIFY by passing a different amount or daily cap."""
        req = self._decide(rid, key)
        approved = _money(amount if amount is not None else req["amount"])
        if approved <= 0:
            raise ApprovalError("approved amount must be positive")
        if self.approved_total() + approved > self.data["ceiling"]:
            raise ApprovalError("approval would exceed the client ceiling")
        modified = approved != req["amount"] or (daily_cap is not None and _money(daily_cap) != req["daily_cap"])
        if daily_cap is not None:
            req["daily_cap"] = _money(daily_cap)
        req.update(status="APPROVED", approved_amount=approved, decided_at=_now(), note=note)
        self._save()
        self._log("principal", "request_modified_and_approved" if modified else "request_approved",
                  request_id=rid, approved_amount=approved, daily_cap=req["daily_cap"])

    def reject(self, rid: str, key: str, note: str = ""):
        req = self._decide(rid, key)
        req.update(status="REJECTED", decided_at=_now(), note=note)
        self._save()
        self._log("principal", "request_rejected", request_id=rid, note=note)

    # ------------------------------------------------------------- gate
    def _under(self, rid: str, excluding: str | None = None):
        return [c for name, c in self.data["campaigns"].items()
                if c["request_id"] == rid and name != excluding]

    def authorize(self, action: dict, today=None):
        """Raise SpendBlocked unless the action is safe or fully covered by an approval."""
        kind = action.get("type")
        if kind in SAFE_ACTIONS:
            return
        if kind not in SPEND_ACTIONS:
            raise SpendBlocked(f"unknown action type {kind!r}; refused by default")
        today = _d(today) if today else date.today()
        name = action.get("campaign")
        existing = self.data["campaigns"].get(name)
        rid = action.get("request_id") or (existing or {}).get("request_id")
        req = self.data["requests"].get(rid)
        if not req:
            raise SpendBlocked("no approval record for this action")
        if req["status"] != "APPROVED":
            raise SpendBlocked(f"{rid} is {req['status']}, not APPROVED")
        if today > _d(req["end"]):
            raise SpendBlocked(f"{rid} expired on {req['end']}")
        if kind != "launch" and not existing:
            raise SpendBlocked(f"campaign {name!r} has not been launched")
        if kind == "launch" and existing:
            raise SpendBlocked(f"campaign {name!r} already exists")
        channel = action.get("channel") or (existing or {}).get("channel")
        if channel != req["channel"]:
            raise SpendBlocked(f"{rid} covers channel {req['channel']!r}, not {channel!r}")
        if req["campaign"] not in ("*", name):
            raise SpendBlocked(f"{rid} covers campaign {req['campaign']!r}, not {name!r}")

        start = _d(action.get("start") or (existing or {}).get("start") or req["start"])
        end = _d(action.get("end") or (existing or {}).get("end") or req["end"])
        if start < _d(req["start"]) or end > _d(req["end"]):
            raise SpendBlocked(f"flight {start}..{end} is outside the approved dates "
                               f"{req['start']}..{req['end']}")
        if kind == "extend_flight":
            return

        budget = _money(action.get("budget", 0))
        daily = _money(action.get("daily_budget", (existing or {}).get("daily_budget", 0)))
        if budget <= 0 or daily <= 0:
            raise SpendBlocked("budget and daily budget must be stated and positive")
        if kind == "increase_budget" and budget <= existing["budget"] and daily <= existing["daily_budget"]:
            raise SpendBlocked("not an increase; use decrease_budget")
        others = self._under(rid, excluding=name)
        committed = _money(sum(c["budget"] for c in others))
        if committed + budget > req["approved_amount"]:
            raise SpendBlocked(f"budget {budget} plus {committed} already committed exceeds "
                               f"the {req['approved_amount']} approved under {rid}")
        live_daily = _money(sum(c["daily_budget"] for c in others if c["status"] == "live"))
        if live_daily + daily > req["daily_cap"]:
            raise SpendBlocked(f"daily budget {daily} plus {live_daily} already live exceeds "
                               f"the daily cap {req['daily_cap']} under {rid}")

    def execute(self, action: dict, adapter, actor: str = "ad-operations-specialist", today=None) -> dict:
        """The only route to an ad platform. Checks the gate, then calls the adapter."""
        name = action.get("campaign")
        try:
            self.authorize(action, today=today)
        except SpendBlocked as blocked:
            self._log(actor, "action_blocked", action=action, reason=str(blocked))
            raise
        kind = action["type"]
        camp = self.data["campaigns"].get(name)
        if kind in SAFE_ACTIONS and not camp:
            raise ApprovalError(f"campaign {name!r} does not exist")
        if kind == "decrease_budget":
            new = _money(action["budget"])
            if new > camp["budget"]:
                raise SpendBlocked("decrease_budget cannot raise the budget")
            if new < self.spent(name):
                raise ApprovalError("budget cannot go below what has already been spent")
        result = adapter.apply(action)
        if kind == "launch":
            req = self.data["requests"][action["request_id"]]
            self.data["campaigns"][name] = {
                "request_id": action["request_id"], "channel": action["channel"],
                "budget": _money(action["budget"]), "daily_budget": _money(action["daily_budget"]),
                "start": str(_d(action.get("start") or req["start"])),
                "end": str(_d(action.get("end") or req["end"])), "status": "live"}
        elif kind == "increase_budget":
            camp["budget"] = _money(action["budget"])
            camp["daily_budget"] = _money(action.get("daily_budget", camp["daily_budget"]))
        elif kind == "decrease_budget":
            camp["budget"] = _money(action["budget"])
            camp["daily_budget"] = min(camp["daily_budget"], _money(action.get("daily_budget", camp["daily_budget"])))
        elif kind == "extend_flight":
            camp["end"] = str(_d(action["end"]))
        elif kind == "pause":
            camp["status"] = "paused"
        self._save()
        self._log(actor, "action_executed", action=action, result=result)
        return result

    # ----------------------------------------------------------- ledger
    def record_spend(self, campaign: str, amount: float, day, actor: str = "budget-controller"):
        if campaign not in self.data["campaigns"]:
            raise ApprovalError(f"campaign {campaign!r} does not exist")
        self.data["spend"].append({"campaign": campaign, "amount": _money(amount), "date": str(_d(day))})
        self._save()
        self._log(actor, "spend_recorded", campaign=campaign, amount=_money(amount), date=str(_d(day)))

    def spent(self, campaign: str | None = None) -> float:
        return _money(sum(s["amount"] for s in self.data["spend"]
                          if campaign is None or s["campaign"] == campaign))

    def ledger(self) -> dict:
        approved = self.approved_total()
        committed = _money(sum(c["budget"] for c in self.data["campaigns"].values()))
        spent = self.spent()
        overspends = [n for n, c in self.data["campaigns"].items() if self.spent(n) > c["budget"]]
        return {"client": self.data["client"], "currency": self.data["currency"],
                "ceiling": self.data["ceiling"], "approved": approved,
                "unapproved_headroom": _money(self.data["ceiling"] - approved),
                "committed": committed, "spent": spent,
                "remaining_of_ceiling": _money(self.data["ceiling"] - spent),
                "pending_requests": [r["id"] for r in self.data["requests"].values() if r["status"] == "PENDING"],
                "campaigns_over_budget": overspends}
