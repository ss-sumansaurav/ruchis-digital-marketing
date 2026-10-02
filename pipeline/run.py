"""Run the data pipeline: (synthetic sources) -> ingest -> dbt build -> dashboard.

  python -m pipeline.run --client demo --synthetic        # dry run on synthetic data
  python -m pipeline.run --client acme --extracts path/   # extracts from a connector

Needs `pip install -r requirements.txt` (duckdb, dbt-duckdb).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

from . import ingest

ROOT = Path(__file__).resolve().parent.parent


def _config() -> dict:
    """Read the flat key: value pairs from config/agency.yaml (no YAML dependency)."""
    cfg = {}
    for line in (ROOT / "config" / "agency.yaml").read_text().splitlines():
        m = re.match(r"^(\w+):\s*\"?([^\"#]*?)\"?\s*(#.*)?$", line)
        if m:
            cfg[m.group(1)] = m.group(2).strip()
    return cfg


def _dbt() -> str:
    found = shutil.which("dbt") or str(Path(sys.executable).with_name("dbt"))
    if not Path(found).exists():
        sys.exit("dbt not found: pip install -r requirements.txt")
    return found


def run(client: str, state_dir: Path, extracts: Path | None = None, synthetic=False,
        as_of: date | None = None, dashboard=True, quiet=False) -> Path:
    state_dir = Path(state_dir).resolve()
    work = state_dir / "pipeline" / client
    db = state_dir / f"{client}.duckdb"
    if synthetic:
        from . import synth
        extracts = work / "extracts"
        synth.build(extracts, state_dir, client=client, as_of=as_of)
    if extracts is None:
        sys.exit("give --extracts, or --synthetic for a dry run")

    counts = ingest.load(db, extracts, state_dir / f"{client}.json")
    if not quiet:
        print("loaded:", json.dumps(counts))

    cfg = _config()
    dbt_vars = {"pacing_tolerance_pct": float(cfg.get("pacing_tolerance_pct", 10)),
                "reconciliation_tolerance_pct": float(cfg.get("reconciliation_tolerance_pct", 2))}
    env = {**os.environ, "RUCHI_WAREHOUSE": str(db), "DBT_PROFILES_DIR": str(ROOT / "warehouse")}
    cmd = [_dbt(), "build", "--project-dir", str(ROOT / "warehouse"), "--target-path", str(work / "dbt-target"),
           "--log-path", str(work / "dbt-logs"), "--vars", json.dumps(dbt_vars)]
    if quiet:
        cmd.append("--quiet")
    proc = subprocess.run(cmd, env=env, capture_output=quiet, text=True)
    if proc.returncode:
        sys.exit(f"dbt build failed{': ' + proc.stdout[-2000:] if quiet else ''}")

    if dashboard:
        from . import dashboard as dash
        out = dash.build(db, ROOT / "workspace" / client / "dashboard.html")
        if not quiet:
            print("dashboard:", out)
    return db


def main(argv=None):
    p = argparse.ArgumentParser(prog="pipeline")
    p.add_argument("--client", required=True)
    p.add_argument("--state-dir", default=str(ROOT / "state"))
    p.add_argument("--extracts", type=Path)
    p.add_argument("--synthetic", action="store_true", help="generate synthetic sources (dry run)")
    p.add_argument("--as-of", type=date.fromisoformat, help="reference date for synthetic data")
    p.add_argument("--no-dashboard", action="store_true")
    a = p.parse_args(argv)
    run(a.client, Path(a.state_dir), a.extracts, a.synthetic, a.as_of, not a.no_dashboard)


if __name__ == "__main__":
    main()
