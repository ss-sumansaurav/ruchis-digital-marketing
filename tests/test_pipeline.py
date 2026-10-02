"""The data pipeline on synthetic data: warehouse builds, metrics agree, planted faults are caught.

Needs duckdb and dbt-duckdb (pip install -r requirements.txt); skipped otherwise.
"""
import csv
import json
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

try:
    import duckdb
except ImportError:  # pragma: no cover
    duckdb = None

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
HAVE_DBT = bool(shutil.which("dbt") or Path(sys.executable).with_name("dbt").exists())


@unittest.skipUnless(duckdb and HAVE_DBT, "needs duckdb and dbt-duckdb")
class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pipeline import run
        cls.tmp = Path(tempfile.mkdtemp())
        cls.db = run.run("demo", cls.tmp, synthetic=True, as_of=date(2026, 10, 2), dashboard=False, quiet=True)
        cls.con = duckdb.connect(str(cls.db), read_only=True)

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        shutil.rmtree(cls.tmp)

    def one(self, sql):
        return self.con.execute(sql).fetchone()

    def test_spend_in_marts_matches_the_platform_extract(self):
        with open(self.tmp / "pipeline/demo/extracts/platform_daily.csv") as f:
            extract = round(sum(float(r["spend"]) for r in csv.DictReader(f)), 2)
        for sql in ("select sum(spend) from marts.mart_campaign_performance",
                    "select sum(spend) from marts.mart_channel_performance",
                    "select spend from marts.mart_exec_overview",
                    "select sum(spend) from marts.mart_channel_daily"):
            self.assertAlmostEqual(self.one(sql)[0], extract, places=2, msg=sql)

    def test_budget_position_matches_the_gate(self):
        state = json.loads((self.tmp / "demo.json").read_text())
        approved = sum(r["approved_amount"] for r in state["requests"].values() if r["status"] == "APPROVED")
        ceiling, appr, committed = self.one("select ceiling, approved, committed from marts.mart_exec_overview")
        self.assertEqual(ceiling, state["ceiling"])
        self.assertEqual(appr, approved)
        self.assertEqual(committed, sum(c["budget"] for c in state["campaigns"].values()))
        self.assertLessEqual(appr, ceiling)

    def test_every_planted_fault_raises_its_alert_and_nothing_else(self):
        found = set(self.con.execute("select rule, campaign from marts.mart_alerts").fetchall())
        expected = {("pacing_deviation", "prog_video"), ("cpa_spike", "search_generic"),
                    ("tracking_break", "social_prospecting"), ("reconciliation", "social_retargeting")}
        self.assertTrue(expected <= found, f"missing: {expected - found}")
        unexpected = {r for r in found - expected if r[0] != "budget_exhaustion"}
        self.assertEqual(unexpected, set())

    def test_no_approval_breach_and_no_overspend(self):
        self.assertEqual(self.one("select count(*) from marts.mart_alerts where rule in ('approval_breach', 'overspend')")[0], 0)

    def test_reconciliation_flags_only_the_mismatched_campaign(self):
        rows = self.con.execute("select campaign, round(difference_pct, 3) from marts.mart_reconciliation "
                                "where not within_tolerance").fetchall()
        self.assertEqual(rows, [("social_retargeting", 0.04)])

    def test_backend_metrics_use_only_days_the_crm_covers(self):
        spend_window, orders, cpa = self.one(
            "select sum(spend_backend_window), sum(backend_orders), "
            "sum(spend_backend_window) / sum(backend_orders) from core.fct_performance_daily")
        mart_cpa = self.one("select spend_backend_window / backend_orders from marts.mart_exec_overview")[0]
        self.assertAlmostEqual(cpa, mart_cpa, places=6)
        crm_as_of = self.one("select crm_as_of from marts.mart_exec_overview")[0]
        late = self.one(f"select count(*) from core.fct_performance_daily where date > '{crm_as_of}' "
                        "and (backend_orders is not null or spend_backend_window <> 0)")[0]
        self.assertEqual(late, 0)

    def test_forecast_is_a_range_capped_at_budget(self):
        for low, base, high, budget in self.con.execute(
                "select forecast_spend_low, forecast_spend_base, forecast_spend_high, budget "
                "from marts.mart_campaign_performance").fetchall():
            self.assertLessEqual(low, base)
            self.assertLessEqual(base, high)
            self.assertLessEqual(high, budget)

    def test_everything_is_labelled_synthetic(self):
        self.assertTrue(self.one("select is_synthetic from marts.mart_exec_overview")[0])
        self.assertEqual(self.one("select count(*) from marts.mart_freshness where not is_synthetic")[0], 0)

    def test_dashboard_labels_synthetic_data_and_freshness(self):
        from pipeline import dashboard
        out = dashboard.build(self.db, self.tmp / "dashboard.html").read_text()
        self.assertIn("Synthetic data.", out)
        self.assertIn("data to 01 Oct 2026", out)
        self.assertIn("CRM, data to 30 Sep 2026", out)

    def test_adhoc_reports_carry_definitions_and_refuse_bare_sql(self):
        from pipeline import adhoc
        header, cols, rows, meta = adhoc.run(self.db, "platform_vs_backend_gap")
        md = adhoc.to_markdown(header, cols, rows, meta)
        for word in ("Period:", "Source:", "Metrics:", "Caveats:", "Synthetic"):
            self.assertIn(word, md)
        bare = self.tmp / "bare.sql"
        bare.write_text("select 1")
        with self.assertRaises(ValueError):
            adhoc.run(self.db, str(bare))

    def test_adhoc_connection_is_read_only(self):
        from pipeline import adhoc
        q = self.tmp / "write.sql"
        q.write_text("-- question: x\n-- period: x\n-- source: x\n-- metrics: x\n-- caveats: x\n"
                     "drop table marts.mart_alerts")
        with self.assertRaises(duckdb.Error):
            adhoc.run(self.db, str(q))


if __name__ == "__main__":
    unittest.main()
