"""Load source extracts and the gate's state into the warehouse's raw schema.

Every source lands as-is in `raw.*`, replaced on each load, with the time it
was loaded. Transformation and every metric definition live in the dbt
project under warehouse/, never here.

Today the extracts come from pipeline/synth.py (dry run). A live connector
(dlt or Meltano, read-only credentials) must write the same five extract
shapes; nothing downstream changes.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb

EXTRACTS = ("platform_daily", "web_sessions", "crm_orders", "plan_daily", "source_freshness")
# Column types for gate tables, so an engagement with no campaigns or spend yet still loads.
GATE_SCHEMAS = {
    "gate_engagement": "client varchar, currency varchar, ceiling double",
    "gate_requests": ('id varchar, campaign varchar, channel varchar, amount double, approved_amount double, '
                      '"start" varchar, "end" varchar, daily_cap double, status varchar, summary varchar, '
                      'requested_at varchar, decided_at varchar'),
    "gate_campaigns": ('campaign varchar, request_id varchar, channel varchar, budget double, daily_budget double, '
                       '"start" varchar, "end" varchar, status varchar'),
    "gate_spend": "campaign varchar, amount double, date varchar",
}


def load(db_path, extract_dir, state_path) -> dict:
    db_path, extract_dir, state_path = Path(db_path), Path(extract_dir), Path(state_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    loaded_at = datetime.now(timezone.utc).replace(tzinfo=None)
    counts = {}
    con = duckdb.connect(str(db_path))
    try:
        con.execute("create schema if not exists raw")
        for name in EXTRACTS:
            src = extract_dir / f"{name}.csv"
            con.execute(f"create or replace table raw.{name} as "
                        f"select *, ?::timestamp as _loaded_at from read_csv_auto(?, header=true)",
                        [loaded_at, str(src)])
            counts[name] = con.execute(f"select count(*) from raw.{name}").fetchone()[0]

        state = json.loads(state_path.read_text())
        requests = [{k: r.get(k) for k in ("id", "campaign", "channel", "amount", "approved_amount", "start",
                                           "end", "daily_cap", "status", "summary", "requested_at", "decided_at")}
                    for r in state["requests"].values()]
        campaigns = [{"campaign": n, **c} for n, c in state["campaigns"].items()]
        tables = {
            "gate_engagement": [{"client": state["client"], "currency": state["currency"], "ceiling": state["ceiling"]}],
            "gate_requests": requests,
            "gate_campaigns": campaigns,
            "gate_spend": state["spend"],
        }
        for name, rows in tables.items():
            cols = [c.split()[0].strip('"') for c in GATE_SCHEMAS[name].split(", ")]
            con.execute(f"create or replace table raw.{name} ({GATE_SCHEMAS[name]}, _loaded_at timestamp)")
            if rows:
                con.executemany(f"insert into raw.{name} values ({', '.join('?' * (len(cols) + 1))})",
                                [[r.get(c) for c in cols] + [loaded_at] for r in rows])
            counts[name] = len(rows)
    finally:
        con.close()
    return counts
