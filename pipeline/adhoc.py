"""Run a saved ad hoc report against the warehouse.

  python -m pipeline.adhoc --client demo weekly_channel_summary
  python -m pipeline.adhoc --client demo path/to/query.sql --csv out.csv

The Ad Hoc Reporting Analyst turns a plain-language question into SQL over the
marts and core tables, saves it in reports/queries/ (or the campaign's
reports/queries/) with the header below, and runs it here. The header is
required so every answer carries its definitions, period, source and caveats:

  -- question: ...
  -- period: ...
  -- source: ...
  -- metrics: ...
  -- caveats: ...

Queries run on a read-only connection.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = ("question", "period", "source", "metrics", "caveats")


def load_query(ref: str) -> tuple[dict, str]:
    path = Path(ref)
    if not path.exists():
        path = ROOT / "reports" / "queries" / f"{ref}.sql"
    text = path.read_text()
    header = dict(re.findall(r"^--\s*(\w+):\s*(.+)$", text, flags=re.M))
    missing = [k for k in REQUIRED if k not in header]
    if missing:
        raise ValueError(f"{path.name} is missing header fields: {', '.join(missing)}")
    return header, text


def run(db_path, ref: str) -> tuple[dict, list[str], list[tuple], dict]:
    header, sql = load_query(ref)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        fresh = con.execute("""select max(case when source = 'ad_platforms' then data_as_of end),
                                      max(case when source = 'crm' then data_as_of end),
                                      bool_or(is_synthetic) from marts.mart_freshness""").fetchone()
        meta = dict(zip(("platform_as_of", "crm_as_of", "synthetic"), fresh))
    finally:
        con.close()
    return header, cols, rows, meta


def to_markdown(header, cols, rows, meta) -> str:
    out = [f"**{header['question']}**", ""]
    if meta.get("synthetic"):
        out += ["_Synthetic dry-run data: not a real client result._", ""]
    out += ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join("" if v is None else f"{v:,}" if isinstance(v, (int, float)) else str(v) for v in r) + " |"
            for r in rows]
    out += ["", f"Period: {header['period']}. Data to: ad platforms {meta.get('platform_as_of')}, CRM {meta.get('crm_as_of')}.",
            f"Source: {header['source']}.", f"Metrics: {header['metrics']}.", f"Caveats: {header['caveats']}"]
    return "\n".join(out)


def main(argv=None):
    p = argparse.ArgumentParser(prog="adhoc")
    p.add_argument("--client", required=True)
    p.add_argument("--state-dir", default=str(ROOT / "state"))
    p.add_argument("query", help="saved query name in reports/queries/, or a path to a .sql file")
    p.add_argument("--csv", type=Path, help="also write the result as CSV")
    a = p.parse_args(argv)
    try:
        header, cols, rows, meta = run(Path(a.state_dir) / f"{a.client}.duckdb", a.query)
    except (ValueError, FileNotFoundError, duckdb.Error) as e:
        sys.exit(f"ERROR: {e}")
    print(to_markdown(header, cols, rows, meta))
    if a.csv:
        with a.csv.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)


if __name__ == "__main__":
    main()
