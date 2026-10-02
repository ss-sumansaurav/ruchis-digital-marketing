select
    cast(date as date)            as date,
    utm_campaign                  as campaign,
    utm_source,
    utm_medium,
    cast(sessions as bigint)      as sessions,
    cast(is_synthetic as boolean) as is_synthetic
from {{ source('raw', 'web_sessions') }}
