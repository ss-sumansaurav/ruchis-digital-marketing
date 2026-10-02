-- question: How did each channel perform week by week?
-- period: ISO weeks of the flight, through the latest complete platform day
-- source: core.fct_performance_daily (ad platforms; backend from CRM)
-- metrics: CPA platform = spend / platform conversions; CPA backend = spend on CRM-covered days / CRM orders (last-touch UTM). Definitions in warehouse/macros/metrics.sql
-- caveats: Platform conversions over-claim. Backend CPA is not incremental. The latest week may be partial and CRM lags one day more than platforms.
select
    date_trunc('week', date)::date                                   as week,
    channel,
    round(sum(spend))                                                as spend,
    sum(platform_conversions)                                        as platform_conversions,
    round(sum(spend) / nullif(sum(platform_conversions), 0))         as cpa_platform,
    sum(backend_orders)                                              as backend_orders,
    round(sum(spend_backend_window) / nullif(sum(backend_orders), 0)) as cpa_backend
from core.fct_performance_daily
where has_platform_data
group by 1, 2
order by 1, 2
