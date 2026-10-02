-- question: How much do the platforms over-claim conversions compared with the CRM?
-- period: Days both the platforms and the CRM cover
-- source: core.fct_performance_daily
-- metrics: Over-claim ratio = platform conversions / CRM orders matched by UTM campaign
-- caveats: A ratio above 1 is expected because every platform credits itself. This is not an incrementality measure; only a holdout or geo test gives that.
select
    channel,
    sum(platform_conversions)                                              as platform_conversions,
    sum(backend_orders)                                                    as crm_orders,
    round(sum(platform_conversions)::double / nullif(sum(backend_orders), 0), 2) as over_claim_ratio
from core.fct_performance_daily
where has_crm_data
group by 1
order by over_claim_ratio desc
