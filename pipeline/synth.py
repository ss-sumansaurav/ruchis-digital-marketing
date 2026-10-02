"""Synthetic source data for dry runs. Every row carries is_synthetic = true.

Builds one demo engagement end to end through the real approval gate
(requests, Principal approval, launches through the execution service,
ledger spend), then writes the ad platform, web analytics and CRM extracts
that the warehouse ingests. Nothing here is a benchmark: the rates are made
up to exercise the pipeline, and some faults are planted on purpose so the
alerts have something to find:

* programmatic under-paces against plan
* generic search CPC jumps over the last three days (CPA spike)
* social prospecting loses its site tracking for two days
* the ledger for social retargeting is 4% below platform spend (reconciliation)
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

from agency.core import Engagement, MockAdapter

DEMO_KEY = "synthetic-demo-key"   # dry-run demo only; real clients use `set-key`

# campaign: channel, request, budget, daily budget, CPM, CTR, site CVR, platform over-claim, pacing
CAMPAIGNS = {
    "search_brand":       ("paid_search",  "SAR-0001", 150_000,  5_800,   900, 0.120, 0.050, 1.10, 0.97),
    "search_generic":     ("paid_search",  "SAR-0001", 420_000, 16_000, 1_500, 0.050, 0.025, 1.15, 0.97),
    "social_prospecting": ("paid_social",  "SAR-0002", 330_000, 12_800,   140, 0.011, 0.012, 1.60, 0.98),
    "social_retargeting": ("paid_social",  "SAR-0002", 150_000,  5_800,   260, 0.018, 0.035, 1.45, 0.97),
    "prog_video":         ("programmatic", "SAR-0003", 240_000,  9_000,   120, 0.004, 0.008, 2.50, 0.70),
}
REQUESTS = [  # id order matters: the gate numbers requests sequentially
    ("paid_search",  600_000, 23_000, "Search envelope: brand and generic"),
    ("paid_social",  500_000, 19_000, "Social envelope: prospecting and retargeting"),
    ("programmatic", 250_000,  9_500, "Programmatic video awareness"),
]
UTM_SOURCE = {"paid_search": "google", "paid_social": "meta", "programmatic": "dv360"}
UTM_MEDIUM = {"paid_search": "cpc", "paid_social": "paid_social", "programmatic": "display"}
AOV = 1_450          # synthetic average order value, INR
NEW_CUSTOMER_SHARE = {"search_brand": 0.35, "social_retargeting": 0.25}
# The KPI and target each plan line is bought against (from the synthetic media plan)
KPI = {"search_brand": ("cpa_backend", 250), "search_generic": ("cpa_backend", 1_300),
       "social_prospecting": ("cpa_backend", 1_300), "social_retargeting": ("cpa_backend", 650),
       "prog_video": ("cpm", 130)}


def _write(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def build(out_dir, state_dir, client="demo", as_of: date | None = None, seed=7) -> dict:
    """Create the demo engagement and source extracts. Returns paths and the flight."""
    rnd = random.Random(seed)
    as_of = as_of or date.today()
    start, end = as_of - timedelta(days=25), as_of + timedelta(days=2)
    flight_days = (end - start).days + 1
    out_dir, state_dir = Path(out_dir), Path(state_dir)
    state_path = state_dir / f"{client}.json"
    for p in (state_path, state_path.with_suffix(".audit.jsonl")):
        p.unlink(missing_ok=True)

    # 1. The engagement goes through the real gate.
    eng = Engagement.create(state_path, client, "INR", 1_500_000)
    eng.set_key(DEMO_KEY)
    for channel, amount, cap, summary in REQUESTS:
        rid = eng.create_request(campaign="*", channel=channel, amount=amount, start=start,
                                 end=end, daily_cap=cap, summary=f"[SYNTHETIC] {summary}")
        eng.approve(rid, DEMO_KEY, note="synthetic dry-run approval")
    adapter = MockAdapter()
    for name, (channel, rid, budget, daily, *_rest) in CAMPAIGNS.items():
        eng.execute({"type": "launch", "campaign": name, "request_id": rid, "channel": channel,
                     "budget": budget, "daily_budget": daily, "start": str(start), "end": str(end)},
                    adapter, today=start)

    # 2. Daily delivery.
    platform, web, crm, plan = [], [], [], []
    order_no = 0
    last_platform_day = as_of - timedelta(days=1)   # platforms report through yesterday
    last_crm_day = as_of - timedelta(days=2)        # CRM export lags a day more
    for name, (channel, rid, budget, daily, cpm, ctr, cvr, claim, pace) in CAMPAIGNS.items():
        for i in range(flight_days):
            day = start + timedelta(days=i)
            plan.append({"date": day, "campaign": name, "channel": channel,
                         "planned_spend": round(budget / flight_days, 2), "kpi": KPI[name][0],
                         "kpi_target": KPI[name][1], "is_synthetic": True})
            if day > last_platform_day:
                continue
            spend = round(daily * pace * rnd.uniform(0.9, 1.04), 2)
            day_cpm = cpm * rnd.uniform(0.92, 1.08)
            if name == "search_generic" and day > last_platform_day - timedelta(days=3):
                day_cpm *= 1.45                      # planted: auction pressure, CPA spike
            impressions = int(spend / day_cpm * 1000)
            clicks = int(impressions * ctr * rnd.uniform(0.9, 1.1))
            sessions = int(clicks * rnd.uniform(0.82, 0.9))
            if name == "social_prospecting" and day in (as_of - timedelta(days=4), as_of - timedelta(days=3)):
                sessions = 0                         # planted: pixel/UTM break
            true_orders = int(round(clicks * 0.86 * cvr * rnd.uniform(0.85, 1.15)))
            p_conv = int(round(true_orders * claim))
            platform.append({"source": channel, "date": day, "campaign": name, "channel": channel,
                             "impressions": impressions, "clicks": clicks, "spend": spend,
                             "platform_conversions": p_conv,
                             "platform_revenue": round(p_conv * AOV * rnd.uniform(0.95, 1.05), 2),
                             "is_synthetic": True})
            web.append({"date": day, "utm_source": UTM_SOURCE[channel], "utm_medium": UTM_MEDIUM[channel],
                        "utm_campaign": name, "sessions": sessions, "is_synthetic": True})
            if day <= last_crm_day:
                for _ in range(true_orders):
                    order_no += 1
                    crm.append({"order_id": f"SYN-{order_no:06d}", "order_date": day, "utm_campaign": name,
                                "revenue": round(rnd.gauss(AOV, 300), 2),
                                "new_customer": rnd.random() < NEW_CUSTOMER_SHARE.get(name, 0.7),
                                "is_synthetic": True})
            # 3. The Budget Controller records spend from invoices into the ledger.
            ledger_amount = spend * (0.96 if name == "social_retargeting" else 1.0)   # planted mismatch
            eng.record_spend(name, ledger_amount, day)

    _write(out_dir / "platform_daily.csv", platform)
    _write(out_dir / "web_sessions.csv", web)
    _write(out_dir / "crm_orders.csv", crm)
    _write(out_dir / "plan_daily.csv", plan)
    _write(out_dir / "source_freshness.csv", [
        {"source": "ad_platforms", "data_as_of": last_platform_day, "is_synthetic": True},
        {"source": "web_analytics", "data_as_of": last_platform_day, "is_synthetic": True},
        {"source": "crm", "data_as_of": last_crm_day, "is_synthetic": True},
        {"source": "plan", "data_as_of": as_of, "is_synthetic": True},
    ])
    return {"state": state_path, "out_dir": out_dir, "start": start, "end": end, "as_of": as_of}
