select
    cast(date as date)              as date,
    campaign,
    channel,
    cast(planned_spend as double)   as planned_spend,
    kpi,
    cast(kpi_target as double)      as kpi_target,
    cast(is_synthetic as boolean)   as is_synthetic
from {{ source('raw', 'plan_daily') }}
