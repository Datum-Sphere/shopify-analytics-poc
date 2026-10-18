-- Mirror financial_coverage without exposing raw payloads or error text.
-- Unknown event dates/currencies deliberately block the selected source globally.
select store_domain,is_synthetic,currency_code,reporting_date,'unsupported_product_event'::text as issue_type
from {{ ref('fct_sales_events') }}
where is_test is not true and (reporting_date is null or currency_code is null or not coalesce(is_supported,false)
   or gross_sales is null or discounts is null or returns_amount is null or net_sales is null)
union all
select o.store_domain,o.is_synthetic,o.shop_currency,null::date,'incomplete_order_extraction'
from {{ ref('stg_orders') }} o
where o.is_test is not true and (o.is_test is null or o.reporting_timezone is null or o.shop_currency is null or not o.has_financial_extraction
   or not exists(select 1 from {{ ref('stg_sales_agreements') }} a where a.order_key=o.order_key))
union all
select s.store_domain,s.is_synthetic,s.currency_code,
       (a.happened_at at time zone o.reporting_timezone)::date,'unsupported_adjustment'
from {{ ref('stg_sales') }} s
left join {{ ref('stg_sales_agreements') }} a using(agreement_key)
left join {{ ref('stg_orders') }} o on a.order_key=o.order_key
where o.is_test is not true and s.sale_type in ('UnknownSale','AdjustmentSale') and (s.total_amount is null or s.total_amount<>0)
union all
select s.store_domain,s.is_synthetic,s.currency_code,null::date,'missing_product_event_parent'
from {{ ref('stg_sales') }} s
where s.line_type='PRODUCT'
  and not exists(select 1 from {{ ref('fct_sales_events') }} f where f.sale_key=s.sale_key)
union all
select f.store_domain,f.is_synthetic,f.currency_code,f.reporting_date,'missing_product_line'
from {{ ref('fct_sales_events') }} f
where f.is_test is not true
  and not exists(select 1 from {{ ref('stg_order_lines') }} l where l.line_key=f.line_key)
