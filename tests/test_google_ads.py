"""Google Ads connector against recorded-shape API responses. No network, no live account."""
import csv
import io
import json
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.connectors.google_ads import GoogleAdsClient, GoogleAdsError, extract  # noqa: E402

ACCOUNT = [{"results": [{"customer": {"resourceName": "customers/1234567890", "id": "1234567890",
                                      "currencyCode": "INR", "timeZone": "Asia/Kolkata"}}]}]


def campaign_rows():
    rows = []
    for day, cost, conv in (("2026-09-29", 15_500_000_000, "11.5"), ("2026-09-30", 14_250_000_000, "9")):
        rows.append({"campaign": {"resourceName": "customers/1234567890/campaigns/111", "id": "111",
                                  "name": "IN | Search | Generic", "advertisingChannelType": "SEARCH",
                                  "status": "ENABLED"},
                     "metrics": {"impressions": "10000", "clicks": "480", "costMicros": str(cost),
                                 "conversions": conv, "conversionsValue": "16675.5"},
                     "segments": {"date": day}})
    rows.append({"campaign": {"id": "222", "name": "IN | PMax | Test", "advertisingChannelType": "PERFORMANCE_MAX"},
                 "metrics": {"impressions": "900", "clicks": "12", "costMicros": "1000000000"},
                 "segments": {"date": "2026-09-30"}})
    return [{"results": rows[:2]}, {"results": rows[2:]}]   # searchStream returns batches


class FakeHTTP:
    """Records requests; answers the token endpoint and searchStream like Google does."""

    def __init__(self, currency="INR"):
        self.requests, self.currency = [], currency

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        if req.full_url.startswith("https://oauth2.googleapis.com/token"):
            body = {"access_token": "ya29.test", "expires_in": 3599}
        else:
            q = json.loads(req.data)["query"]
            if "FROM customer" in q:
                body = json.loads(json.dumps(ACCOUNT))
                body[0]["results"][0]["customer"]["currencyCode"] = self.currency
            else:
                body = campaign_rows()
        return io.BytesIO(json.dumps(body).encode())


class GoogleAdsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.http = FakeHTTP()
        self.client = GoogleAdsClient("dev-token", "cid", "secret", "refresh", login_customer_id="987-654-3210",
                                      opener=self.http)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_extract(self, **kw):
        return extract(self.client, "123-456-7890", self.tmp, currency="INR",
                       campaign_map={"111": "search_generic"}, today=date(2026, 10, 2), **kw)

    def rows(self):
        with (self.tmp / "platform_daily.csv").open() as f:
            return list(csv.DictReader(f))

    def test_writes_the_platform_daily_extract(self):
        result = self.run_extract()
        rows = self.rows()
        self.assertEqual(result["rows"], 3)
        self.assertEqual(rows[0]["campaign"], "search_generic")
        self.assertEqual(rows[0]["channel"], "paid_search")
        self.assertEqual(float(rows[0]["spend"]), 15_500.0)          # cost_micros / 1e6
        self.assertEqual(float(rows[0]["platform_conversions"]), 11.5)  # fractional conversions kept
        self.assertEqual(rows[0]["is_synthetic"], "False")
        self.assertEqual(result["spend"], 15_500 + 14_250 + 1_000)

    def test_window_ends_yesterday_in_the_account_time_zone(self):
        result = self.run_extract(days=30)
        self.assertEqual((result["start"], result["end"]), ("2026-09-02", "2026-10-01"))
        query = json.loads(self.http.requests[-1].data)["query"]
        self.assertIn("BETWEEN '2026-09-02' AND '2026-10-01'", query)
        with (self.tmp / "source_freshness.csv").open() as f:
            self.assertEqual(list(csv.DictReader(f)),
                             [{"source": "ad_platforms", "data_as_of": "2026-10-01", "is_synthetic": "False"}])

    def test_unmapped_campaigns_are_kept_and_reported(self):
        result = self.run_extract()
        self.assertEqual(result["unmapped_campaigns"], ["IN | PMax | Test"])
        self.assertIn("IN | PMax | Test", [r["campaign"] for r in self.rows()])

    def test_currency_mismatch_stops_the_run(self):
        self.http.currency = "USD"
        with self.assertRaises(GoogleAdsError):
            self.run_extract()
        self.assertFalse((self.tmp / "platform_daily.csv").exists())

    def test_sends_the_right_headers_and_never_a_mutate_call(self):
        self.run_extract()
        api_calls = [r for r in self.http.requests if "googleads.googleapis.com" in r.full_url]
        for r in api_calls:
            self.assertTrue(r.full_url.endswith("/customers/1234567890/googleAds:searchStream"), r.full_url)
            self.assertIn("/v25/", r.full_url)
            self.assertEqual(r.get_header("Developer-token"), "dev-token")
            self.assertEqual(r.get_header("Login-customer-id"), "9876543210")
            self.assertEqual(r.get_header("Authorization"), "Bearer ya29.test")
        self.assertFalse(any("mutate" in r.full_url for r in self.http.requests))

    def test_the_connector_has_no_write_code(self):
        source = (ROOT / "pipeline/connectors/google_ads.py").read_text()
        self.assertNotIn(":mutate", source)
        self.assertNotIn("Service/", source)

    def test_bad_customer_id_is_refused(self):
        with self.assertRaises(GoogleAdsError):
            extract(self.client, "12345", self.tmp, currency="INR", today=date(2026, 10, 2))

    def test_missing_credentials_are_named(self):
        with self.assertRaises(GoogleAdsError) as e:
            GoogleAdsClient.from_env()
        self.assertIn("GOOGLE_ADS_DEVELOPER_TOKEN", str(e.exception))


try:
    import duckdb  # noqa: F401
    from pipeline.run import _dbt  # noqa: F401
    HAVE_STACK = bool(shutil.which("dbt") or Path(sys.executable).with_name("dbt").exists())
except ImportError:
    HAVE_STACK = False


@unittest.skipUnless(HAVE_STACK, "needs duckdb and dbt-duckdb")
class GoogleAdsIntoWarehouseTest(unittest.TestCase):
    """A real-shaped Google Ads extract, with no CRM, web or plan data yet, still builds the warehouse."""

    def test_google_ads_only_engagement_builds(self):
        import duckdb
        from agency import Engagement, MockAdapter
        from pipeline import run
        tmp = Path(tempfile.mkdtemp())
        try:
            eng = Engagement.create(tmp / "acme.json", "acme", "INR", 500_000)
            eng.set_key("principal-secret")
            rid = eng.create_request(campaign="*", channel="paid_search", amount=300_000, start="2026-09-01",
                                     end="2026-10-31", daily_cap=20_000, summary="search")
            eng.approve(rid, "principal-secret")
            eng.execute({"type": "launch", "campaign": "search_generic", "request_id": rid, "channel": "paid_search",
                         "budget": 300_000, "daily_budget": 16_000}, MockAdapter(), today="2026-09-01")
            ext = tmp / "extracts"
            client = GoogleAdsClient("d", "c", "s", "r", opener=FakeHTTP())
            extract(client, "1234567890", ext, currency="INR", campaign_map={"111": "search_generic"},
                    today=date(2026, 10, 2))
            db = run.run("acme", tmp, extracts=ext, dashboard=False, quiet=True)
            from pipeline import dashboard
            page = dashboard.build(db, tmp / "dash.html").read_text()
            self.assertIn("CRM: no data connected yet", page)
            self.assertNotIn("Synthetic data.", page)
            con = duckdb.connect(str(db), read_only=True)
            spend, synthetic = con.execute("select spend, is_synthetic from marts.mart_exec_overview").fetchone()
            self.assertEqual(spend, 30_750.0)
            self.assertFalse(synthetic)
            alerts = con.execute("select rule, campaign from marts.mart_alerts where rule = 'unapproved_spend'").fetchall()
            self.assertEqual(alerts, [("unapproved_spend", "IN | PMax | Test")])
            con.close()
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
