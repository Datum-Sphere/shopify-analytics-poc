-- One current product per store/product ID, with missing-catalog fallback.
with keys as (
    select product_key from {{ ref('stg_products') }}
    union
    select product_key from {{ ref('stg_order_lines') }} where product_key is not null
), line_titles as (
    select product_key, min(title) as title, bool_or(is_synthetic) as is_synthetic, min(store_domain) as store_domain
    from {{ ref('stg_order_lines') }} group by product_key
)
select k.product_key, coalesce(p.store_domain, l.store_domain) as store_domain,
       coalesce(p.is_synthetic, l.is_synthetic) as is_synthetic,
       coalesce(p.title, l.title) as title, p.status,
       p.product_key is null as missing_catalog_record
from keys k
left join {{ ref('stg_products') }} p using (product_key)
left join line_titles l using (product_key)
