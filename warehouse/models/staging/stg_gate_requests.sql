select
    id                                  as request_id,
    campaign                            as campaign_scope,
    channel,
    cast(amount as double)              as requested_amount,
    cast(approved_amount as double)     as approved_amount,
    cast("start" as date)               as start_date,
    cast("end" as date)                 as end_date,
    cast(daily_cap as double)           as daily_cap,
    status,
    summary,
    cast(requested_at as timestamp)     as requested_at,
    cast(decided_at as timestamp)       as decided_at
from {{ source('raw', 'gate_requests') }}
