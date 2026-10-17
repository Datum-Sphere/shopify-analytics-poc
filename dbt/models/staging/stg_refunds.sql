select store_domain || '|' || source_id as refund_key,
       store_domain || '|' || parent_source_id as order_key,
       store_domain, is_synthetic, source_id as refund_id,
       (payload->>'createdAt')::timestamptz as created_at,
       (payload->>'processedAt')::timestamptz as processed_at,
       (payload->>'updatedAt')::timestamptz as updated_at,
       (payload#>>'{totalRefundedSet,shopMoney,amount}')::numeric as payment_refunded_amount,
       payload#>>'{totalRefundedSet,shopMoney,currencyCode}' as currency_code
from {{ source('shopify_raw', 'shopify_records') }}
where entity = 'refund'
