{#
  Impressions to revenue, overall and by channel. Sessions come from web analytics,
  orders and revenue from the CRM, restricted to the window both sources cover so
  each stage rate compares like with like.
#}
with f as (select * from {{ ref('fct_performance_daily') }} where has_crm_data),
by_level as (
    select 'All channels' as level, impressions, clicks, sessions, backend_orders, backend_revenue,
           new_customers, spend from f
    union all
    select channel, impressions, clicks, sessions, backend_orders, backend_revenue, new_customers, spend from f
)
select
    level,
    sum(impressions) as impressions, sum(clicks) as clicks, sum(sessions) as sessions,
    sum(backend_orders) as orders, sum(backend_revenue) as revenue, sum(new_customers) as new_customers,
    sum(spend) as spend,
    {{ ctr('sum(clicks)', 'sum(impressions)') }}           as ctr,
    {{ safe_div('sum(sessions)', 'sum(clicks)') }}         as click_to_session,
    {{ cvr('sum(backend_orders)', 'sum(sessions)') }}      as cvr,
    {{ cpm('sum(spend)', 'sum(impressions)') }}            as cpm,
    {{ cpc('sum(spend)', 'sum(clicks)') }}                 as cpc,
    {{ cpa('sum(spend)', 'sum(backend_orders)') }}         as cpa_backend,
    {{ roas('sum(backend_revenue)', 'sum(spend)') }}       as roas_backend,
    {{ cac('sum(spend)', 'sum(new_customers)') }}          as cac
from by_level group by 1
