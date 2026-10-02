{# Platform-reported spend against the budget ledger, per campaign. #}
select
    campaign, channel, request_id,
    spend as platform_spend,
    ledger_spend,
    spend - ledger_spend as difference,
    {{ safe_div('spend - ledger_spend', 'spend') }} as difference_pct,
    abs(coalesce({{ safe_div('spend - ledger_spend', 'spend') }}, 0)) * 100
        <= {{ var('reconciliation_tolerance_pct') }} as within_tolerance
from {{ ref('mart_campaign_performance') }}
