-- Two later partial reversals on the same order/line; cash-only refund adds no return.
{% if var('validate_financial_fixtures', true) %}
select 'refund allocation' as problem where
 (select sum(returns_amount) from {{ ref('fct_returns') }} where store_domain='financial-fixtures.invalid') <> 180
 or (select sum(line_subtotal) from {{ ref('fct_refund_lines') }} where store_domain='financial-fixtures.invalid') <> 180
 or (select sum(payment_refunded_amount) from {{ ref('fct_refunds') }} where store_domain='financial-fixtures.invalid') <> 213
 or (select count(*) from {{ ref('fct_returns') }} where store_domain='financial-fixtures.invalid') <> 2
 or (select count(*) from {{ ref('fct_refunds') }} where store_domain='financial-fixtures.invalid' and refund_line_count=0) <> 1
{% else %}
select 1 where false
{% endif %}
