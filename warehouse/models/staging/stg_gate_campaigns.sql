select
    campaign,
    request_id,
    channel,
    cast(budget as double)          as budget,
    cast(daily_budget as double)    as daily_budget,
    cast("start" as date)           as start_date,
    cast("end" as date)             as end_date,
    status
from {{ source('raw', 'gate_campaigns') }}
