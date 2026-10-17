-- Fail visibly instead of silently publishing unsupported product adjustments.
select sale_key as failing_key from {{ ref('fct_sales_events') }}
where not coalesce(is_supported, false)
union all
select order_key from {{ ref('stg_orders') }} o
where not has_financial_extraction
   or not exists (select 1 from {{ ref('stg_sales_agreements') }} a where a.order_key=o.order_key)
union all
select sale_key from {{ ref('stg_sales') }}
where sale_type in ('UnknownSale', 'AdjustmentSale') and total_amount <> 0
