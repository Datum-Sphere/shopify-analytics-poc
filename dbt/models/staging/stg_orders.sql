select
    store_domain || '|' || source_id as order_key,
    store_domain, is_synthetic, source_id as order_id,
    payload->>'name' as order_name,
    (payload->>'test')::boolean as is_test,
    (payload->>'createdAt')::timestamptz as created_at,
    (payload->>'processedAt')::timestamptz as processed_at,
    (payload->>'cancelledAt')::timestamptz as cancelled_at,
    payload->>'displayFinancialStatus' as financial_status,
    payload#>>'{_shop,ianaTimezone}' as reporting_timezone,
    payload#>>'{_shop,currencyCode}' as shop_currency,
    payload ? 'agreements' as has_financial_extraction
from {{ source('shopify_raw', 'shopify_records') }}
where entity = 'order'
