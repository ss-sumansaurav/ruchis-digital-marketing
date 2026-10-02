select client, currency, cast(ceiling as double) as ceiling
from {{ source('raw', 'gate_engagement') }}
