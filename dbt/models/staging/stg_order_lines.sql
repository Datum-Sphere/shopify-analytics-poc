select
    store_domain || '|' || source_id as line_key,
    store_domain || '|' || parent_source_id as order_key,
    store_domain || '|' || (payload#>>'{product,id}') as product_key,
    store_domain, is_synthetic, source_id as line_id,
    payload->>'title' as title, payload->>'sku' as sku,
    (payload->>'quantity')::integer as quantity,
    (payload#>>'{originalUnitPriceSet,shopMoney,amount}')::numeric as original_unit_price,
    payload#>>'{originalUnitPriceSet,shopMoney,currencyCode}' as currency_code,
    -- Aggregate the allocations inside each line; never expand allocations across sales.
    coalesce((select sum((a#>>'{allocatedAmountSet,shopMoney,amount}')::numeric)
              from jsonb_array_elements(coalesce(payload->'discountAllocations', '[]'::jsonb)) a), 0) as allocated_discount
from {{ source('shopify_raw', 'shopify_records') }}
where entity = 'order_line_item'
