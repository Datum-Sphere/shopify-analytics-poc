-- Check daily rollup against the event ledger independently of the metric identity.
with events as (
 select store_domain,is_synthetic,currency_code,
        sum(gross_sales) as gross_sales,sum(discounts) as discounts,sum(returns_amount) as returns_amount,sum(net_sales) as net_sales
 from {{ ref('fct_sales_events') }} where not is_test
 group by store_domain,is_synthetic,currency_code
), daily as (
 select store_domain,is_synthetic,currency_code,
        sum(gross_sales) as gross_sales,sum(discounts) as discounts,sum(returns_amount) as returns_amount,sum(net_sales) as net_sales
 from {{ ref('mart_daily_sales') }} group by store_domain,is_synthetic,currency_code
)
(select * from events except select * from daily)
union all
(select * from daily except select * from events)
