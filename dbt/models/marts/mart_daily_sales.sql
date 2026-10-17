-- Grain: dataset/store/shop currency/store-local agreement date.
select store_domain, is_synthetic, currency_code, reporting_date,
       count(*) as product_event_count,
       count(*) filter (where not coalesce(is_supported, false)) as unsupported_event_count,
       case when bool_and(coalesce(is_supported, false)) then sum(gross_sales) end as gross_sales,
       case when bool_and(coalesce(is_supported, false)) then sum(discounts) end as discounts,
       case when bool_and(coalesce(is_supported, false)) then sum(gross_returns) end as gross_returns,
       case when bool_and(coalesce(is_supported, false)) then sum(discounts_returned) end as discounts_returned,
       case when bool_and(coalesce(is_supported, false)) then sum(returns_amount) end as returns_amount,
       case when bool_and(coalesce(is_supported, false)) then sum(net_sales) end as net_sales
from {{ ref('fct_sales_events') }}
where is_test = false
group by store_domain, is_synthetic, currency_code, reporting_date
