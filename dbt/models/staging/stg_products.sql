select store_domain || '|' || source_id as product_key,
       store_domain, is_synthetic, source_id as product_id,
       payload->>'title' as title, payload->>'status' as status,
       (payload->>'updatedAt')::timestamptz as updated_at
from {{ source('shopify_raw', 'shopify_records') }}
where entity = 'product'
