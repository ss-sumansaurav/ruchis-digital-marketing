with f as (select * from {{ ref('fct_performance_daily') }} where has_platform_data),
agg as (
select
    date, channel,
    sum(planned_spend) as planned_spend,
    sum(impressions) as impressions, sum(clicks) as clicks, sum(spend) as spend,
    sum(platform_conversions) as platform_conversions, sum(platform_revenue) as platform_revenue,
    sum(sessions) as sessions, sum(backend_orders) as backend_orders,
    sum(backend_revenue) as backend_revenue, sum(new_customers) as new_customers,
    sum(spend_backend_window) as spend_backend_window,
    bool_or(is_synthetic) as is_synthetic,
    'x' as _end
from f
group by 1, 2
)
select * exclude (_end), {{ metric_columns() }} from agg
