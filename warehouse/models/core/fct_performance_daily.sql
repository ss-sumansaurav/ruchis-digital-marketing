{# One row per campaign per day of the planned flight. The single source for every mart. #}
with freshness as (
    select
        max(case when source = 'ad_platforms'  then data_as_of end) as platform_as_of,
        max(case when source = 'web_analytics' then data_as_of end) as web_as_of,
        max(case when source = 'crm'           then data_as_of end) as crm_as_of
    from {{ ref('stg_source_freshness') }}
),
plan as (select * from {{ ref('stg_plan_daily') }}),
platform as (select * from {{ ref('stg_platform_daily') }}),
web as (
    select date, campaign, sum(sessions) as sessions
    from {{ ref('stg_web_sessions') }} group by 1, 2
),
crm as (
    select date, campaign,
           count(*) as backend_orders,
           sum(revenue) as backend_revenue,
           count(*) filter (where new_customer) as new_customers
    from {{ ref('stg_crm_orders') }} group by 1, 2
),
ledger as (
    select date, campaign, sum(ledger_spend) as ledger_spend
    from {{ ref('stg_gate_spend') }} group by 1, 2
),
spine as (
    select date, campaign, channel from plan
    union
    select date, campaign, channel from platform
),
joined as (
    select
        s.date,
        s.campaign,
        s.channel,
        g.request_id,
        plan.kpi,
        plan.kpi_target,
        coalesce(plan.planned_spend, 0)                     as planned_spend,
        s.date <= f.platform_as_of                          as has_platform_data,
        s.date <= f.crm_as_of                               as has_crm_data,
        coalesce(p.impressions, 0)                          as impressions,
        coalesce(p.clicks, 0)                               as clicks,
        coalesce(p.spend, 0)                                as spend,
        coalesce(p.platform_conversions, 0)                 as platform_conversions,
        coalesce(p.platform_revenue, 0)                     as platform_revenue,
        case when s.date <= f.web_as_of then coalesce(w.sessions, 0) end as sessions,
        case when s.date <= f.crm_as_of then coalesce(c.backend_orders, 0) end  as backend_orders,
        case when s.date <= f.crm_as_of then coalesce(c.backend_revenue, 0) end as backend_revenue,
        case when s.date <= f.crm_as_of then coalesce(c.new_customers, 0) end   as new_customers,
        case when s.date <= f.crm_as_of then coalesce(p.spend, 0) else 0 end    as spend_backend_window,
        coalesce(l.ledger_spend, 0)                         as ledger_spend,
        coalesce(p.is_synthetic, plan.is_synthetic, false)  as is_synthetic
    from spine s
    cross join freshness f
    left join plan     on plan.date = s.date and plan.campaign = s.campaign
    left join platform p on p.date = s.date and p.campaign = s.campaign
    left join web w      on w.date = s.date and w.campaign = s.campaign
    left join crm c      on c.date = s.date and c.campaign = s.campaign
    left join ledger l   on l.date = s.date and l.campaign = s.campaign
    left join {{ ref('stg_gate_campaigns') }} g on g.campaign = s.campaign
)
select *, {{ metric_columns() }}
from joined
