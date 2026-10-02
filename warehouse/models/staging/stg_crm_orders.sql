select
    order_id,
    cast(order_date as date)        as date,
    utm_campaign                    as campaign,
    cast(revenue as double)         as revenue,
    cast(new_customer as boolean)   as new_customer,
    cast(is_synthetic as boolean)   as is_synthetic
from {{ source('raw', 'crm_orders') }}
