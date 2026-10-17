-- Grain: one product Sale ID per store. All monetary inputs are event totals.
with events as (
    select s.*, a.order_key, a.refund_key, a.agreement_type, a.happened_at,
           o.is_test, o.reporting_timezone, l.product_key,
           (a.happened_at at time zone o.reporting_timezone)::date as reporting_date,
           abs(s.total_amount) - abs(s.tax_amount) as net_magnitude,
           abs(s.discount_before_tax) as discount_magnitude,
           (s.sale_type='ProductSale' and s.action_type in ('ORDER', 'RETURN') and s.discount_after_tax = 0
            and s.currencies_match and s.currency_code = o.shop_currency
            and abs(s.total_amount) >= abs(s.tax_amount)
            and s.quantity is not null and s.line_key is not null) as is_supported
    from {{ ref('stg_sales') }} s
    join {{ ref('stg_sales_agreements') }} a using (agreement_key)
    join {{ ref('stg_orders') }} o on a.order_key = o.order_key
    left join {{ ref('stg_order_lines') }} l on s.line_key = l.line_key
    where s.line_type = 'PRODUCT'
), metrics as (
    select *,
      case when is_supported then case when action_type='ORDER' then net_magnitude + discount_magnitude else 0 end end as gross_sales,
      case when is_supported then case when action_type='ORDER' then discount_magnitude else 0 end end as discounts,
      case when is_supported then case when action_type='RETURN' then net_magnitude + discount_magnitude else 0 end end as gross_returns,
      case when is_supported then case when action_type='RETURN' then discount_magnitude else 0 end end as discounts_returned,
      case when is_supported then case when action_type='RETURN' then net_magnitude else 0 end end as returns_amount
    from events
)
select *, gross_sales - discounts - returns_amount as net_sales
from metrics
