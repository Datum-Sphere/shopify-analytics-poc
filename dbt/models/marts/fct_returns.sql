-- Financial merchandise reversals, not cash refunds or physical receipt counts.
select sale_key as return_event_key, order_key, line_key, product_key, refund_key,
       store_domain, is_synthetic, is_test, reporting_date, currency_code,
       agreement_type, abs(quantity) as reversed_quantity,
       gross_returns, discounts_returned, returns_amount, is_supported
from {{ ref('fct_sales_events') }} where action_type='RETURN'
