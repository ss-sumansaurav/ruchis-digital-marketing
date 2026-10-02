{#
  Campaign totals to date with pacing and a spend forecast to the end of the flight.
  Forecast method (stated so it can be challenged): remaining days x the lowest,
  mean and highest daily spend of the last 7 reported days, capped at the
  campaign budget because the platform stops delivery at the budget.
#}
with f as (select * from {{ ref('fct_performance_daily') }}),
ref_date as (select max(date) filter (where has_platform_data) as platform_as_of from f),
totals as (
    select
        campaign, channel, request_id, any_value(kpi) as kpi, any_value(kpi_target) as kpi_target,
        sum(planned_spend)                                           as planned_spend_flight,
        sum(planned_spend) filter (where has_platform_data)          as planned_spend_to_date,
        sum(impressions) as impressions, sum(clicks) as clicks, sum(spend) as spend,
        sum(platform_conversions) as platform_conversions, sum(platform_revenue) as platform_revenue,
        sum(sessions) as sessions, sum(backend_orders) as backend_orders,
        sum(backend_revenue) as backend_revenue, sum(new_customers) as new_customers,
        sum(spend_backend_window) as spend_backend_window,
        sum(ledger_spend) as ledger_spend,
        count(*) filter (where not has_platform_data)                as days_remaining,
        bool_or(is_synthetic) as is_synthetic
    from f group by 1, 2, 3
),
recent as (
    select f.campaign, min(spend) as low_daily, avg(spend) as mean_daily, max(spend) as high_daily
    from f, ref_date
    where f.has_platform_data and f.date > ref_date.platform_as_of - interval 7 day
    group by 1
)
select
    t.*,
    r.mean_daily,
    c.budget, c.daily_budget, c.status, c.start_date, c.end_date,
    {{ safe_div('t.spend', 'c.budget') }}                              as budget_used,
    {{ safe_div('t.spend', 't.planned_spend_to_date') }} - 1           as pacing_vs_plan,
    least(c.budget, t.spend + t.days_remaining * r.low_daily)          as forecast_spend_low,
    least(c.budget, t.spend + t.days_remaining * r.mean_daily)         as forecast_spend_base,
    least(c.budget, t.spend + t.days_remaining * r.high_daily)         as forecast_spend_high,
    t.spend + t.days_remaining * r.high_daily > c.budget               as would_exceed_budget_uncapped,
    {{ metric_columns() }},
    case t.kpi
        when 'cpa_backend' then {{ cpa('t.spend_backend_window', 't.backend_orders') }}
        when 'cpm' then {{ cpm('t.spend', 't.impressions') }}
    end                                                                as kpi_actual
from totals t
left join {{ ref('stg_gate_campaigns') }} c using (campaign)
left join recent r using (campaign)
