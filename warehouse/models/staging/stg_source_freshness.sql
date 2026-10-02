select
    source,
    cast(data_as_of as date)        as data_as_of,
    cast(_loaded_at as timestamp)   as loaded_at,
    cast(is_synthetic as boolean)   as is_synthetic
from {{ source('raw', 'source_freshness') }}
