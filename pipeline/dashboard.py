"""Render the warehouse marts as one self-contained HTML dashboard.

This is the interim dashboard: a static page rebuilt on every pipeline run,
reading only marts.* so it can never disagree with the warehouse. The hosted
open-source dashboard (Superset, Metabase OSS or Grafana) reads the same marts.
Every tile states the date its data runs to.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

import duckdb


def _rows(con, sql):
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _money(v, cur="₹"):
    if v is None:
        return "–"
    v = float(v)
    if abs(v) >= 1e7:
        return f"{cur}{v / 1e7:.2f} cr"
    if abs(v) >= 1e5:
        return f"{cur}{v / 1e5:.2f} L"
    return f"{cur}{v:,.0f}"


def _num(v, d=0):
    return "–" if v is None else f"{float(v):,.{d}f}"


def _pct(v, d=1, sign=False):
    return "–" if v is None else f"{float(v) * 100:{'+' if sign else ''}.{d}f}%"


def _x(v):
    return "–" if v is None else f"{float(v):.2f}x"


def _esc(v):
    return html.escape(str(v))


def _is_num(cell) -> bool:
    text = re.sub(r"<[^>]+>", "", str(cell)).strip()
    return bool(re.match(r"^[₹+\-–\d][\d.,%x L cr–₹/]*$", text))


def _table(headers, rows, caption=""):
    numeric = [bool(rows) and all(_is_num(r[i]) for r in rows) for i in range(len(headers))]
    cls = lambda i: " class='r'" if numeric[i] else ""
    th = "".join(f"<th scope='col'{cls(i)}>{_esc(h)}</th>" for i, h in enumerate(headers))
    body = "".join("<tr>" + "".join(f"<td{cls(i)}>{c}</td>" for i, c in enumerate(r)) + "</tr>"
                   for r in rows)
    cap = f"<caption>{_esc(caption)}</caption>" if caption else ""
    return f"<div class='tw'><table>{cap}<thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>"


def _spend_chart(points):
    """Cumulative spend against cumulative plan. Two series, one axis."""
    if not points:
        return ""
    w, h, pl, pr, pt, pb = 960, 260, 64, 64, 12, 28
    n = len(points)
    top = max(max(p["plan_cum"] for p in points), max((p["spend_cum"] or 0) for p in points)) * 1.05
    x = lambda i: pl + (w - pl - pr) * (i / max(n - 1, 1))
    y = lambda v: pt + (h - pt - pb) * (1 - v / top)
    plan = " ".join(f"{x(i):.1f},{y(p['plan_cum']):.1f}" for i, p in enumerate(points))
    act = [(i, p) for i, p in enumerate(points) if p["spend_cum"] is not None]
    actual = " ".join(f"{x(i):.1f},{y(p['spend_cum']):.1f}" for i, p in act)
    grid = "".join(
        f"<line x1='{pl}' x2='{w - pr}' y1='{y(top * k / 4):.1f}' y2='{y(top * k / 4):.1f}' class='grid'/>"
        f"<text x='{pl - 6}' y='{y(top * k / 4) + 4:.1f}' class='ax' text-anchor='end'>{_money(top * k / 4)}</text>"
        for k in range(0, 5))
    ticks = "".join(f"<text x='{x(i):.1f}' y='{h - 8}' class='ax' text-anchor='middle'>{p['date'].strftime('%d %b')}</text>"
                    for i, p in enumerate(points) if i % 7 == 0 or i == n - 1)
    hits = "".join(
        f"<rect x='{x(i) - (w - pl - pr) / n / 2:.1f}' y='{pt}' width='{(w - pl - pr) / n:.1f}' height='{h - pt - pb}' "
        f"class='hit'><title>{p['date']:%d %b}: spend {_money(p['spend_cum'])}, plan {_money(p['plan_cum'])}</title></rect>"
        for i, p in enumerate(points))
    li, lp = act[-1]
    return (f"<svg viewBox='0 0 {w} {h}' role='img' aria-label='Cumulative spend against plan'>{grid}{ticks}"
            f"<polyline points='{plan}' class='plan'/><polyline points='{actual}' class='act'/>"
            f"<circle cx='{x(li):.1f}' cy='{y(lp['spend_cum']):.1f}' r='4' class='dot'/>"
            f"<text x='{x(n - 1) + 6:.1f}' y='{y(points[-1]['plan_cum']) + 4:.1f}' class='lab'>Plan</text>"
            f"<text x='{x(li) + 8:.1f}' y='{y(lp['spend_cum']) + 14:.1f}' class='lab'>Spend</text>{hits}</svg>")


CSS = """
:root{--paper:#F2F3F8;--surface:#FFFFFF;--ink:#1B2040;--muted:#5B6180;--line:#D8DBE8;--tint:#E8EAF4;
--accent:#E2A300;--accent-soft:#FBF1D2;--go:#17735F;--go-soft:#DDF1EB;--stop:#B4372C;--stop-soft:#F8E1DE;
--series:#3D4BD8;--body:"Public Sans","Segoe UI",system-ui,sans-serif}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--paper:#13162A;--surface:#1C2040;--ink:#ECEEF8;
--muted:#A4AAC8;--line:#343A64;--tint:#262B52;--accent:#F0B429;--accent-soft:#3D3312;--go:#4CC3A5;--go-soft:#173A33;
--stop:#F08A7E;--stop-soft:#43201D;--series:#9AA5FF}}
:root[data-theme="dark"]{--paper:#13162A;--surface:#1C2040;--ink:#ECEEF8;--muted:#A4AAC8;--line:#343A64;--tint:#262B52;
--accent:#F0B429;--accent-soft:#3D3312;--go:#4CC3A5;--go-soft:#173A33;--stop:#F08A7E;--stop-soft:#43201D;--series:#9AA5FF}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:400 15px/1.5 var(--body)}
.wrap{max-width:68rem;margin:0 auto;padding:0 16px 48px}h1{font-size:1.5rem;margin:18px 0 4px}h2{font-size:1.1rem;margin:0 0 8px}
.syn{background:var(--accent-soft);border:1px solid var(--accent);border-radius:8px;padding:8px 12px;margin:10px 0 16px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:14px}
.tile,.panel{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px}
.panel{margin-bottom:14px}.k{font-size:.8rem;color:var(--muted)}.v{font-size:1.35rem;font-weight:600;font-variant-numeric:tabular-nums}
.asof{font-size:.75rem;color:var(--muted);margin-top:2px}.muted{color:var(--muted)}.small{font-size:.85rem}
.tw{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.875rem;font-variant-numeric:tabular-nums}
caption{text-align:left;color:var(--muted);font-size:.8rem;padding-bottom:4px}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap}th{color:var(--muted);font-weight:600;text-align:left}
.r{text-align:right}.sev{display:inline-block;border-radius:999px;padding:0 8px;font-size:.75rem;font-weight:600}
.sev.act{background:var(--stop-soft);color:var(--stop)}.sev.review{background:var(--accent-soft);color:var(--ink)}
.ok{color:var(--go)}.bad{color:var(--stop)}
svg{width:100%;height:auto}.grid{stroke:var(--line);stroke-width:1}.ax{fill:var(--muted);font-size:11px}
.plan{fill:none;stroke:var(--muted);stroke-width:2;stroke-dasharray:5 4}.act{fill:none;stroke:var(--series);stroke-width:2}
.dot{fill:var(--series);stroke:var(--surface);stroke-width:2}.lab{fill:var(--ink);font-size:12px}
.hit{fill:transparent}.hit:hover{fill:var(--tint);opacity:.5}
.legend{display:flex;gap:16px;font-size:.8rem;color:var(--muted)}.sw{display:inline-block;width:18px;height:0;border-top:2px solid var(--series);vertical-align:middle;margin-right:6px}
.sw.p{border-top:2px dashed var(--muted)}
"""


def build(db_path, out_path) -> Path:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        ov = _rows(con, "select * from marts.mart_exec_overview")[0]
        camps = _rows(con, "select * from marts.mart_campaign_performance order by channel, campaign")
        chans = _rows(con, "select * from marts.mart_channel_performance order by spend desc")
        funnel = _rows(con, "select * from marts.mart_funnel order by level = 'All channels' desc, spend desc")
        appr = _rows(con, "select * from marts.mart_approvals order by request_id")
        alerts = _rows(con, "select * from marts.mart_alerts order by severity, rule, campaign")
        recon = _rows(con, "select * from marts.mart_reconciliation order by campaign")
        fresh = _rows(con, "select * from marts.mart_freshness order by source")
        pts = _rows(con, """
            select date, sum(sum(planned_spend)) over (order by date) as plan_cum,
                   case when bool_or(has_platform_data) then sum(sum(spend)) over (order by date) end as spend_cum
            from core.fct_performance_daily group by date order by date""")
    finally:
        con.close()

    pa, ca = ov["platform_as_of"], ov["crm_as_of"]
    asof = lambda d, what="Ad platforms": (f"<div class='asof'>{what}, data to {d:%d %b %Y}</div>" if d
                                           else f"<div class='asof'>{what}: no data connected yet</div>")
    day = lambda d: f"{d:%d %b}" if d else "not connected"
    tile = lambda k, v, note: f"<div class='tile'><div class='k'>{k}</div><div class='v'>{v}</div>{note}</div>"
    synthetic = ov["is_synthetic"]
    fs, fe = ov["flight_start"], ov["flight_end"]

    tiles = "".join([
        tile("Client ceiling", _money(ov["ceiling"]), "<div class='asof'>Approval gate, live</div>"),
        tile("Approved", _money(ov["approved"]), f"<div class='asof'>{ov['pending_requests']} pending · gate, live</div>"),
        tile("Spent", _money(ov["spend"]), asof(pa)),
        tile("Remaining of ceiling", _money(ov["remaining_of_ceiling"]), asof(pa)),
        tile("Pacing vs plan", _pct(ov["pacing_vs_plan"], sign=True), asof(pa)),
        tile("Forecast spend at end of flight",
             f"{_money(ov['forecast_spend_low'])}–{_money(ov['forecast_spend_high'])}",
             f"<div class='asof'>base {_money(ov['forecast_spend_base'])} · run-rate method</div>"),
        tile("Backend CPA vs target", f"{_money(ov['actual_cpa_backend'])} / {_money(ov['target_cpa_backend'])}",
             asof(ca, "CRM")),
        tile("ROAS, platform vs backend", f"{_x(ov['roas_platform'])} / {_x(ov['roas_backend'])}",
             asof(ca, "Platforms and CRM")),
        tile("Open alerts", str(ov["open_alerts"]), asof(pa)),
    ])

    alert_rows = [[f"<span class='sev {a['severity']}'>{_esc(a['severity'])}</span>", _esc(a["rule"].replace('_', ' ')),
                   _esc(a["campaign"]), f"<span style='white-space:normal'>{_esc(a['detail'])}</span>"] for a in alerts]
    camp_rows = [[_esc(c["campaign"]), _esc(c["channel"]), _money(c["budget"]), _money(c["spend"]),
                  _pct(c["pacing_vs_plan"], sign=True), _num(c["impressions"]), _num(c["clicks"]), _pct(c["ctr"], 2),
                  _money(c["cpc"]), _money(c["cpa_platform"]), _money(c["cpa_backend"]),
                  f"{_esc(c['kpi'])} {_money(c['kpi_actual'])} / {_money(c['kpi_target'])}",
                  f"{_money(c['forecast_spend_low'])}–{_money(c['forecast_spend_high'])}"] for c in camps]
    chan_rows = [[_esc(c["channel"]), _money(c["budget"]), _money(c["spend"]), _pct(c["pacing_vs_plan"], sign=True),
                  _money(c["cpm"]), _pct(c["ctr"], 2), _money(c["cpc"]), _pct(c["cvr"], 2), _money(c["cpa_platform"]),
                  _money(c["cpa_backend"]), _x(c["roas_platform"]), _x(c["roas_backend"]), _money(c["cac"])] for c in chans]
    fun_rows = [[_esc(f["level"]), _num(f["impressions"]), _num(f["clicks"]), _num(f["sessions"]), _num(f["orders"]),
                 _money(f["revenue"]), _pct(f["ctr"], 2), _pct(f["click_to_session"]), _pct(f["cvr"], 2),
                 _money(f["cpa_backend"]), _x(f["roas_backend"]), _money(f["cac"])] for f in funnel]
    appr_rows = [[_esc(a["request_id"]), _esc(a["channel"]), _esc(a["status"]), _money(a["approved_amount"]),
                  _money(a["daily_cap"]), f"{a['start_date']:%d %b}–{a['end_date']:%d %b}", _money(a["committed"]),
                  _money(a["platform_spend"]), _pct(a["approval_used"]), _money(a["remaining_of_approval"])] for a in appr]
    rec_rows = [[_esc(r["campaign"]), _money(r["platform_spend"]), _money(r["ledger_spend"]), _money(r["difference"]),
                 _pct(r["difference_pct"], 2),
                 "<span class='ok'>within tolerance</span>" if r["within_tolerance"] else "<span class='bad'>outside tolerance</span>"]
                for r in recon]
    fresh_rows = [[_esc(f["source"]), f"{f['data_as_of']:%d %b %Y}", f"{f['loaded_at']:%d %b %Y %H:%M} UTC",
                   "synthetic" if f["is_synthetic"] else "real"] for f in fresh]

    banner = ("<div class='syn'><strong>Synthetic data.</strong> Every figure on this page comes from the dry-run "
              "generator, not from a real client or platform. No money has moved.</div>") if synthetic else ""
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{_esc(ov['client'])} dashboard</title>
<style>{CSS}</style></head><body><div class="wrap">
<h1>{_esc(ov['client'])}: campaign dashboard</h1>
<div class="muted small">Flight {day(fs)}–{day(fe)} · currency {_esc(ov['currency'])} ·
ad platform data to {day(pa)}, CRM data to {day(ca)}. Ad platforms report with a lag and restate conversions, so nothing here is live.</div>
{banner}
<div class="tiles">{tiles}</div>
<div class="panel"><h2>Alerts</h2>{_table(['Severity', 'Rule', 'Campaign', 'Detail'], alert_rows) if alerts else '<p class="muted">No open alerts.</p>'}
<div class="asof">Act: the Head of Performance acts today (pausing or decreasing needs no approval). Review: next optimisation review.</div></div>
<div class="panel"><h2>Cumulative spend against plan</h2>
<div class="legend"><span><span class="sw"></span>Spend (ad platforms)</span><span><span class="sw p"></span>Plan</span></div>
{_spend_chart(pts)}{asof(pa)}</div>
<div class="panel"><h2>Channels</h2>{_table(['Channel', 'Budget', 'Spend', 'Pacing', 'CPM', 'CTR', 'CPC', 'CVR', 'CPA platform', 'CPA backend', 'ROAS platform', 'ROAS backend', 'CAC'], chan_rows)}
<div class="asof">Platform figures to {day(pa)}; backend (CRM, last-touch UTM) to {day(ca)}. Platform conversions over-claim; neither column is incremental.</div></div>
<div class="panel"><h2>Campaigns</h2>{_table(['Campaign', 'Channel', 'Budget', 'Spend', 'Pacing', 'Impr.', 'Clicks', 'CTR', 'CPC', 'CPA platform', 'CPA backend', 'KPI actual / target', 'Forecast spend'], camp_rows)}{asof(pa)}</div>
<div class="panel"><h2>Funnel</h2>{_table(['Level', 'Impressions', 'Clicks', 'Sessions', 'Orders', 'Revenue', 'CTR', 'Click to session', 'CVR', 'CPA', 'ROAS', 'CAC'], fun_rows)}
<div class="asof">Window both web analytics and CRM cover: to {day(ca)}. Orders and revenue from CRM.</div></div>
<div class="panel"><h2>Approvals</h2>{_table(['Request', 'Channel', 'Status', 'Approved', 'Daily cap', 'Dates', 'Committed', 'Spent', 'Used', 'Remaining'], appr_rows)}{asof(pa, 'Gate live; spend from ad platforms')}</div>
<div class="panel"><h2>Spend reconciliation</h2>{_table(['Campaign', 'Platform spend', 'Ledger spend', 'Difference', 'Difference %', 'Status'], rec_rows)}{asof(pa)}</div>
<div class="panel"><h2>Data freshness</h2>{_table(['Source', 'Data to', 'Loaded', 'Type'], fresh_rows)}</div>
<p class="muted small">Metric definitions: warehouse/macros/metrics.sql. Built from the warehouse marts by pipeline/dashboard.py.</p>
</div></body></html>"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page)
    return out_path
