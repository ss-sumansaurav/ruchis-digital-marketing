{#
  Rule-based alerts, one row per open issue. Severity "act" means the Head of
  Performance acts today (a pause or decrease needs no approval); "review" means
  it goes into the next optimisation review. Thresholds are dbt vars set from
  config/agency.yaml.
#}
with f as (select * from {{ ref('fct_performance_daily') }}),
c as (select * from {{ ref('mart_campaign_performance') }}),
ref_date as (select max(date) filter (where has_platform_data) as d from f),

overspend as (
    select 'overspend', 'act', campaign, channel,
           'Platform spend of ' || round(spend)::varchar || ' is above the campaign budget of '
           || round(budget)::varchar || '. Pause or decrease now.',
           spend, budget
    from c where spend > budget
),
exhaustion as (
    select 'budget_exhaustion', 'review', campaign, channel,
           'At the last 7 days'' average run-rate the budget runs out about '
           || round(days_remaining - (budget - spend) / mean_daily, 1)::varchar
           || ' day(s) before the flight ends. Lower the daily budget to spread it, or accept the early finish.',
           days_remaining - (budget - spend) / mean_daily, 1
    from c where mean_daily > 0 and days_remaining - (budget - spend) / mean_daily >= 1
),
pacing as (
    select 'pacing_deviation', case when abs(pacing_vs_plan) > 2 * {{ var('pacing_tolerance_pct') }} / 100.0 then 'act' else 'review' end,
           campaign, channel,
           'Spend is ' || round(pacing_vs_plan * 100, 1)::varchar || '% against plan to date (tolerance '
           || {{ var('pacing_tolerance_pct') }}::varchar || '%).',
           pacing_vs_plan, {{ var('pacing_tolerance_pct') }} / 100.0
    from c where abs(pacing_vs_plan) > {{ var('pacing_tolerance_pct') }} / 100.0
),
cpa_windows as (
    select f.campaign, f.channel,
           {{ cpa("sum(spend) filter (where f.date > ref_date.d - interval 3 day)",
                  "sum(platform_conversions) filter (where f.date > ref_date.d - interval 3 day)") }} as cpa_last3,
           sum(platform_conversions) filter (where f.date > ref_date.d - interval 3 day) as conv_last3,
           {{ cpa("sum(spend) filter (where f.date <= ref_date.d - interval 3 day and f.date > ref_date.d - interval 10 day)",
                  "sum(platform_conversions) filter (where f.date <= ref_date.d - interval 3 day and f.date > ref_date.d - interval 10 day)") }} as cpa_prior7
    from f, ref_date where f.has_platform_data group by 1, 2
),
cpa_spike as (
    select 'cpa_spike', 'review', campaign, channel,
           'Platform CPA over the last 3 days is ' || round(cpa_last3)::varchar || ' against '
           || round(cpa_prior7)::varchar || ' for the 7 days before (x' || round(cpa_last3 / cpa_prior7, 2)::varchar || ').',
           cpa_last3, cpa_prior7 * {{ var('cpa_spike_ratio') }}
    from cpa_windows
    where cpa_last3 > cpa_prior7 * {{ var('cpa_spike_ratio') }}
      and conv_last3 >= {{ var('cpa_spike_min_conversions') }}   -- too few conversions is noise, not a spike
),
tracking as (
    select 'tracking_break', 'act', campaign, channel,
           'No web sessions recorded on ' || strftime(date, '%Y-%m-%d') || ' despite ' || clicks::varchar
           || ' platform clicks. Check the pixel, tag and UTMs.',
           sessions, null
    from f where has_platform_data and clicks >= 100 and coalesce(sessions, 0) = 0 and sessions is not null
),
recon as (
    select 'reconciliation', 'review', campaign, channel,
           'Ledger spend differs from platform spend by ' || round(difference_pct * 100, 1)::varchar
           || '% (' || round(difference)::varchar || '). Reconcile against the invoice.',
           difference_pct, {{ var('reconciliation_tolerance_pct') }} / 100.0
    from {{ ref('mart_reconciliation') }} where not within_tolerance
),
unapproved as (
    select 'unapproved_spend', 'act', campaign, channel,
           'Spend of ' || round(spend)::varchar || ' on a campaign the execution service never launched, so no approval covers it. '
           || 'If it was set up directly in the platform, pause it and raise a Spend Approval Request; if it is ours, add it to the campaign map.',
           spend, 0
    from c where request_id is null and spend > 0
),
approval_breach as (
    select 'approval_breach', 'act', request_id, channel,
           'Committed or live daily budget is above what ' || request_id || ' approved. The gate should make this impossible: investigate.',
           committed, approved_amount
    from {{ ref('mart_approvals') }}
    where status = 'APPROVED' and (committed > approved_amount or live_daily_budget > daily_cap or platform_spend > approved_amount)
)
select a.*, ref_date.d as data_as_of
from (
    select * from overspend union all select * from exhaustion union all select * from pacing union all select * from cpa_spike
    union all select * from tracking union all select * from recon union all select * from unapproved union all select * from approval_breach
) a(rule, severity, campaign, channel, detail, value, threshold), ref_date
