{# Every Spend Approval Request with what was committed and spent against it. #}
with camp as (
    select request_id,
           sum(budget) as committed,
           sum(daily_budget) filter (where status = 'live') as live_daily_budget,
           count(*) as campaigns
    from {{ ref('stg_gate_campaigns') }} group by 1
),
spend as (
    select request_id, sum(spend) as platform_spend, sum(ledger_spend) as ledger_spend
    from {{ ref('fct_performance_daily') }} group by 1
)
select
    r.request_id, r.channel, r.campaign_scope, r.status, r.summary,
    r.requested_amount, r.approved_amount, r.daily_cap, r.start_date, r.end_date,
    r.requested_at, r.decided_at,
    coalesce(camp.campaigns, 0) as campaigns,
    coalesce(camp.committed, 0) as committed,
    coalesce(camp.live_daily_budget, 0) as live_daily_budget,
    coalesce(spend.platform_spend, 0) as platform_spend,
    coalesce(spend.ledger_spend, 0) as ledger_spend,
    r.approved_amount - coalesce(spend.platform_spend, 0) as remaining_of_approval,
    {{ safe_div('coalesce(spend.platform_spend, 0)', 'r.approved_amount') }} as approval_used
from {{ ref('stg_gate_requests') }} r
left join camp using (request_id)
left join spend using (request_id)
