select store_domain || '|' || source_id as refund_line_key,
       store_domain || '|' || parent_source_id as refund_key,
       store_domain || '|' || (payload#>>'{lineItem,id}') as line_key,
       store_domain, is_synthetic, source_id as refund_line_id,
       (payload->>'quantity')::integer as quantity,
       payload->>'restockType' as restock_type,
       (payload#>>'{subtotalSet,shopMoney,amount}')::numeric as line_subtotal,
       (payload#>>'{totalTaxSet,shopMoney,amount}')::numeric as line_tax,
       payload#>>'{subtotalSet,shopMoney,currencyCode}' as currency_code
from {{ source('shopify_raw', 'shopify_records') }}
where entity = 'refund_line_item'
