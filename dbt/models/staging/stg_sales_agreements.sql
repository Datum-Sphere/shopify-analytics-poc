select store_domain || '|' || source_id as agreement_key,
       store_domain || '|' || parent_source_id as order_key,
       store_domain || '|' || (payload#>>'{refund,id}') as refund_key,
       store_domain, is_synthetic, source_id as agreement_id,
       payload->>'__typename' as agreement_type,
       payload->>'reason' as reason,
       (payload->>'happenedAt')::timestamptz as happened_at
from {{ source('shopify_raw', 'shopify_records') }}
where entity = 'sales_agreement'
