select store_domain from {{ source('shopify_raw','shopify_records') }}
where is_synthetic <> (store_domain like '%.invalid')
union all
select s.store_domain from {{ ref('stg_sales') }} s
join {{ ref('stg_sales_agreements') }} a using(agreement_key)
join {{ ref('stg_orders') }} o on a.order_key=o.order_key
where s.is_synthetic<>a.is_synthetic or a.is_synthetic<>o.is_synthetic
union all
select r.store_domain from {{ ref('stg_refund_lines') }} r
join {{ ref('stg_refunds') }} f using(refund_key)
where r.is_synthetic<>f.is_synthetic or r.currency_code<>f.currency_code
