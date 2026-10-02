{# Shown on every dashboard tile: how current each source is. Never present delayed data as live. #}
select source, data_as_of, loaded_at, is_synthetic
from {{ ref('stg_source_freshness') }}
