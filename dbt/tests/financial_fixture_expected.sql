-- Exact fixture rows, including local midnight, later returns and USD segregation.
{% if var('validate_financial_fixtures', true) %}
with actual as (
 select store_domain,currency_code,reporting_date,gross_sales,discounts,returns_amount,net_sales
 from {{ ref('mart_daily_sales') }} where is_synthetic and store_domain='financial-fixtures.invalid'
), expected as (
 select store_domain,currency_code,reporting_date::date,gross_sales::numeric,discounts::numeric,returns_amount::numeric,net_sales::numeric
 from {{ ref('expected_daily_sales') }}
)
(select * from actual except select * from expected)
union all
(select * from expected except select * from actual)
{% else %}
select 1 where false
{% endif %}
