select 'product event grain' as problem
where (select count(*) from {{ ref('stg_sales') }} where line_type='PRODUCT')
   <> (select count(*) from {{ ref('fct_sales_events') }})
union all
select 'return event grain'
where (select count(*) from {{ ref('fct_sales_events') }} where action_type='RETURN')
   <> (select count(*) from {{ ref('fct_returns') }})
union all
select 'refund line grain'
where (select count(*) from {{ ref('stg_refund_lines') }} )
   <> (select count(*) from {{ ref('fct_refund_lines') }})
union all
select 'daily grain'
where exists (
 select 1 from {{ ref('mart_daily_sales') }} group by store_domain,is_synthetic,currency_code,reporting_date having count(*)<>1
)
