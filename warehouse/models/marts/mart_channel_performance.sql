with c as (select * from {{ ref('mart_campaign_performance') }}),
agg as (
select
    channel,
    count(*) as campaigns,
    sum(budget) as budget, sum(planned_spend_to_date) as planned_spend_to_date,
    sum(impressions) as impressions, sum(clicks) as clicks, sum(spend) as spend,
    sum(platform_conversions) as platform_conversions, sum(platform_revenue) as platform_revenue,
    sum(sessions) as sessions, sum(backend_orders) as backend_orders,
    sum(backend_revenue) as backend_revenue, sum(new_customers) as new_customers,
    sum(spend_backend_window) as spend_backend_window,
    sum(forecast_spend_low) as forecast_spend_low, sum(forecast_spend_base) as forecast_spend_base,
    sum(forecast_spend_high) as forecast_spend_high,
    {{ safe_div('sum(spend)', 'sum(planned_spend_to_date)') }} - 1 as pacing_vs_plan,
    'x' as _end
from c group by 1
)
select * exclude (_end), {{ metric_columns() }} from agg
