select
    cast(date as date)                 as date,
    campaign,
    channel,
    source                             as platform,
    cast(impressions as bigint)        as impressions,
    cast(clicks as bigint)             as clicks,
    cast(spend as double)              as spend,
    cast(platform_conversions as double) as platform_conversions,
    cast(platform_revenue as double)   as platform_revenue,
    cast(is_synthetic as boolean)      as is_synthetic
from {{ source('raw', 'platform_daily') }}
