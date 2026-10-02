select
    campaign,
    cast(date as date)      as date,
    cast(amount as double)  as ledger_spend
from {{ source('raw', 'gate_spend') }}
