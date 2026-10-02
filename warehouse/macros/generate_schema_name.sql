{# Use the folder schema name as-is (staging, core, marts) instead of prefixing it. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
  {{ custom_schema_name if custom_schema_name else target.schema }}
{%- endmacro %}
