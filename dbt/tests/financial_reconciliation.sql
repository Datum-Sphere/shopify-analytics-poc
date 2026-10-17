select sale_key as failing_key from {{ ref('fct_sales_events') }}
where net_sales <> gross_sales - discounts - returns_amount
   or returns_amount <> gross_returns - discounts_returned
   or (action_type='ORDER' and net_sales <> abs(total_amount)-abs(tax_amount))
   or (action_type='RETURN' and net_sales <> -(abs(total_amount)-abs(tax_amount)))
   or least(gross_sales, discounts, returns_amount, gross_returns, discounts_returned) < 0
union all
select store_domain || '|' || reporting_date::text from {{ ref('mart_daily_sales') }}
where net_sales <> gross_sales - discounts - returns_amount or unsupported_event_count <> 0
