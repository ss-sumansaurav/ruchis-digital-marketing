"""Google Ads reporting connector: read-only, writes the platform_daily extract.

  python -m pipeline.connectors.google_ads --client acme --customer-id 1234567890 \
      --campaign-map workspace/acme/google-ads-campaigns.json --out state/pipeline/acme/extracts

What it does
* Calls the Google Ads API (REST, `googleAds:searchStream`) for campaign x day
  delivery: impressions, clicks, cost, conversions, conversion value.
* Re-pulls a trailing window on every run (default 30 days), because Google Ads
  restates conversions after the fact. The warehouse load replaces the window.
* Writes platform_daily.csv in the shape pipeline/ingest.py expects, and the
  ad_platforms row of source_freshness.csv (yesterday in the account's time zone:
  today is never complete).
* Refuses to run if the account's currency differs from the engagement's.

What it never does
* It has no code path that writes to Google Ads. Launches, budgets and pauses go
  only through the execution service and the approval gate.
* It should run with credentials for a Google Ads user that has the **Read only**
  access level. Google's OAuth scope (`adwords`) cannot itself be limited to
  reading, so the access level on the account is what makes it read-only.

Credentials come from the environment (never from the repository or a chat):
  GOOGLE_ADS_DEVELOPER_TOKEN, GOOGLE_ADS_CLIENT_ID, GOOGLE_ADS_CLIENT_SECRET,
  GOOGLE_ADS_REFRESH_TOKEN, and GOOGLE_ADS_LOGIN_CUSTOMER_ID when access is
  through a manager account.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

API_VERSION = "v25"   # latest major version on 2 Oct 2026 (v25.2, 23 Sep 2026); Google sunsets old versions
API = "https://googleads.googleapis.com/{version}/customers/{cid}/googleAds:searchStream"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# Google Ads advertising_channel_type -> the agency's channel names (gate and warehouse)
CHANNELS = {
    "SEARCH": "paid_search", "PERFORMANCE_MAX": "performance_max", "VIDEO": "online_video",
    "DISPLAY": "display", "DEMAND_GEN": "demand_gen", "SHOPPING": "shopping", "MULTI_CHANNEL": "app",
}

QUERY = """
SELECT segments.date, campaign.id, campaign.name, campaign.advertising_channel_type,
       campaign.status, metrics.impressions, metrics.clicks, metrics.cost_micros,
       metrics.conversions, metrics.conversions_value
FROM campaign
WHERE segments.date BETWEEN '{start}' AND '{end}'
  AND metrics.impressions > 0
"""
ACCOUNT_QUERY = "SELECT customer.id, customer.currency_code, customer.time_zone FROM customer"


class GoogleAdsError(Exception):
    pass


class GoogleAdsClient:
    def __init__(self, developer_token, client_id, client_secret, refresh_token,
                 login_customer_id=None, version=API_VERSION, opener=urllib.request.urlopen):
        self.developer_token, self.client_id = developer_token, client_id
        self.client_secret, self.refresh_token = client_secret, refresh_token
        self.login_customer_id = _digits(login_customer_id) if login_customer_id else None
        self.version, self._open, self._token = version, opener, None

    @classmethod
    def from_env(cls, **kw):
        need = ("GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET",
                "GOOGLE_ADS_REFRESH_TOKEN")
        missing = [n for n in need if not os.environ.get(n)]
        if missing:
            raise GoogleAdsError(f"missing environment variables: {', '.join(missing)}")
        return cls(*(os.environ[n] for n in need), os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID"), **kw)

    def _access_token(self) -> str:
        if not self._token:
            body = urllib.parse.urlencode({"client_id": self.client_id, "client_secret": self.client_secret,
                                           "refresh_token": self.refresh_token, "grant_type": "refresh_token"})
            with self._open(urllib.request.Request(TOKEN_URL, data=body.encode()), timeout=30) as r:
                self._token = json.loads(r.read())["access_token"]
        return self._token

    def search(self, customer_id: str, query: str) -> list[dict]:
        url = API.format(version=self.version, cid=_digits(customer_id))
        headers = {"Authorization": f"Bearer {self._access_token()}", "developer-token": self.developer_token,
                   "Content-Type": "application/json"}
        if self.login_customer_id:
            headers["login-customer-id"] = self.login_customer_id
        req = urllib.request.Request(url, data=json.dumps({"query": query}).encode(), headers=headers)
        try:
            with self._open(req, timeout=120) as r:
                batches = json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise GoogleAdsError(f"Google Ads API {e.code}: {e.read()[:500]!r}") from None
        return [row for batch in batches for row in batch.get("results", [])]


def _digits(cid) -> str:
    d = re.sub(r"\D", "", str(cid))
    if len(d) != 10:
        raise GoogleAdsError(f"customer id should have 10 digits, got {cid!r}")
    return d


def extract(client: GoogleAdsClient, customer_id: str, out_dir, *, currency: str,
            campaign_map: dict | None = None, days: int = 30, today: date | None = None) -> dict:
    """Pull the trailing window and write platform_daily.csv plus the freshness row.

    campaign_map maps Google Ads campaign id (or exact name) to the agency's campaign
    name in the gate, so spend lines up with approvals. Unmapped campaigns are kept
    under their Google Ads name and reported, never dropped."""
    account = client.search(customer_id, ACCOUNT_QUERY)[0]["customer"]
    if account["currencyCode"] != currency:
        raise GoogleAdsError(f"account currency {account['currencyCode']} does not match engagement currency {currency}")
    tz_today = today or datetime.now(ZoneInfo(account["timeZone"])).date()
    end = tz_today - timedelta(days=1)               # today is never complete
    start = end - timedelta(days=days - 1)
    rows = client.search(customer_id, QUERY.format(start=start, end=end))

    campaign_map, unmapped, out = campaign_map or {}, set(), []
    for r in rows:
        c, m = r["campaign"], r.get("metrics", {})
        name = campaign_map.get(str(c["id"])) or campaign_map.get(c["name"])
        if not name:
            unmapped.add(c["name"])
            name = c["name"]
        out.append({
            "source": "google_ads", "date": r["segments"]["date"], "campaign": name,
            "channel": CHANNELS.get(c.get("advertisingChannelType", ""), "google_ads_other"),
            "impressions": int(m.get("impressions", 0)), "clicks": int(m.get("clicks", 0)),
            "spend": round(int(m.get("costMicros", 0)) / 1_000_000, 2),
            "platform_conversions": round(float(m.get("conversions", 0)), 2),
            "platform_revenue": round(float(m.get("conversionsValue", 0)), 2),
            "is_synthetic": False,
        })

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = ["source", "date", "campaign", "channel", "impressions", "clicks", "spend",
              "platform_conversions", "platform_revenue", "is_synthetic"]
    with (out_dir / "platform_daily.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)
    _set_freshness(out_dir / "source_freshness.csv", "ad_platforms", end)
    return {"rows": len(out), "start": str(start), "end": str(end), "unmapped_campaigns": sorted(unmapped),
            "spend": round(sum(r["spend"] for r in out), 2), "account_time_zone": account["timeZone"]}


def _set_freshness(path: Path, source: str, as_of: date):
    rows = []
    if path.exists():
        with path.open() as f:
            rows = [r for r in csv.DictReader(f) if r["source"] != source]
    rows.append({"source": source, "data_as_of": str(as_of), "is_synthetic": False})
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["source", "data_as_of", "is_synthetic"])
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    p = argparse.ArgumentParser(prog="google_ads")
    p.add_argument("--client", required=True, help="agency client name (for the currency check)")
    p.add_argument("--customer-id", required=True, help="Google Ads customer id, with or without dashes")
    p.add_argument("--out", type=Path, required=True, help="extract folder for pipeline.run --extracts")
    p.add_argument("--campaign-map", type=Path, help="JSON: Google Ads campaign id or name -> agency campaign")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--state-dir", type=Path, default=Path("state"))
    a = p.parse_args(argv)
    try:
        currency = json.loads((a.state_dir / f"{a.client}.json").read_text())["currency"]
        cmap = json.loads(a.campaign_map.read_text()) if a.campaign_map else None
        result = extract(GoogleAdsClient.from_env(), a.customer_id, a.out, currency=currency,
                         campaign_map=cmap, days=a.days)
    except (GoogleAdsError, FileNotFoundError) as e:
        sys.exit(f"ERROR: {e}")
    print(json.dumps(result, indent=2))
    if result["unmapped_campaigns"]:
        print("WARNING: campaigns not in the campaign map; add them so spend lines up with approvals.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
