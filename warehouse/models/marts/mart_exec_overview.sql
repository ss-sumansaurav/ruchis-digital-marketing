{# One row: the executive view of the engagement. #}
with e as (select * from {{ ref('stg_gate_engagement') }}),
c as (select * from {{ ref('mart_campaign_performance') }}),
r as (select * from {{ ref('stg_gate_requests') }}),
fr as (select * from {{ ref('mart_freshness') }}),
agg as (
    select
        sum(budget) as committed, sum(spend) as spend, sum(ledger_spend) as ledger_spend,
        sum(planned_spend_to_date) as planned_spend_to_date, sum(planned_spend_flight) as planned_spend_flight,
        sum(forecast_spend_low) as forecast_spend_low, sum(forecast_spend_base) as forecast_spend_base,
        sum(forecast_spend_high) as forecast_spend_high,
        sum(impressions) as impressions, sum(clicks) as clicks, sum(sessions) as sessions,
        sum(platform_conversions) as platform_conversions, sum(platform_revenue) as platform_revenue,
        sum(backend_orders) as backend_orders, sum(backend_revenue) as backend_revenue,
        sum(new_customers) as new_customers, sum(spend_backend_window) as spend_backend_window,
        {{ safe_div('sum(kpi_target * backend_orders) filter (where kpi = \'cpa_backend\')',
                    'sum(backend_orders) filter (where kpi = \'cpa_backend\')') }} as target_cpa_backend,
        {{ cpa('sum(spend_backend_window) filter (where kpi = \'cpa_backend\')',
               'sum(backend_orders) filter (where kpi = \'cpa_backend\')') }} as actual_cpa_backend,
        min(start_date) as flight_start, max(end_date) as flight_end,
        bool_or(is_synthetic) as is_synthetic
    from c
)
select
    e.client, e.currency, e.ceiling,
    (select sum(approved_amount) from r where status = 'APPROVED') as approved,
    (select count(*) from r where status = 'PENDING') as pending_requests,
    agg.*,
    e.ceiling - agg.spend as remaining_of_ceiling,
    {{ safe_div('agg.spend', 'agg.planned_spend_to_date') }} - 1 as pacing_vs_plan,
    {{ metric_columns() }},
    (select data_as_of from fr where source = 'ad_platforms') as platform_as_of,
    (select data_as_of from fr where source = 'crm') as crm_as_of,
    (select count(*) from {{ ref('mart_alerts') }}) as open_alerts
from e cross join agg
