{#
  The agency's metric definitions. Every report, mart and dashboard tile uses
  these macros, so a metric means the same thing everywhere. Change a
  definition here and nowhere else.

  Platform-reported metrics use the ad platform's own conversion counts,
  which over-claim because each platform credits itself. "Backend" metrics use
  CRM orders matched by UTM campaign (last-touch). Neither is incremental:
  incrementality comes only from experiments (geo tests, holdouts) or MMM.
#}
{% macro safe_div(num, den) -%} ({{ num }})::double / nullif(({{ den }})::double, 0) {%- endmacro %}

{% macro cpm(spend, impressions) -%} {{ safe_div(spend ~ ' * 1000', impressions) }} {%- endmacro %}
{% macro ctr(clicks, impressions) -%} {{ safe_div(clicks, impressions) }} {%- endmacro %}
{% macro cpc(spend, clicks) -%} {{ safe_div(spend, clicks) }} {%- endmacro %}
{# Site conversion rate: backend orders per landed session #}
{% macro cvr(orders, sessions) -%} {{ safe_div(orders, sessions) }} {%- endmacro %}
{% macro cpa(spend, conversions) -%} {{ safe_div(spend, conversions) }} {%- endmacro %}
{% macro roas(revenue, spend) -%} {{ safe_div(revenue, spend) }} {%- endmacro %}
{# Customer acquisition cost: spend per new customer (backend) #}
{% macro cac(spend, new_customers) -%} {{ safe_div(spend, new_customers) }} {%- endmacro %}

{# Backend metrics divide by spend_backend_window: spend on days the CRM export
   already covers, so its reporting lag does not deflate CPA or inflate ROAS. #}

{# Append the full metric set to a select that has the base measures. #}
{% macro metric_columns() -%}
    {{ cpm('spend', 'impressions') }}                    as cpm,
    {{ ctr('clicks', 'impressions') }}                   as ctr,
    {{ cpc('spend', 'clicks') }}                         as cpc,
    {{ cvr('backend_orders', 'sessions') }}              as cvr,
    {{ cpa('spend', 'platform_conversions') }}           as cpa_platform,
    {{ cpa('spend_backend_window', 'backend_orders') }}  as cpa_backend,
    {{ roas('platform_revenue', 'spend') }}              as roas_platform,
    {{ roas('backend_revenue', 'spend') }}               as roas_backend,
    {{ cac('spend_backend_window', 'new_customers') }}   as cac
{%- endmacro %}
