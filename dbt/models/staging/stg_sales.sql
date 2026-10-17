select store_domain || '|' || source_id as sale_key,
       store_domain || '|' || parent_source_id as agreement_key,
       store_domain || '|' || (payload#>>'{lineItem,id}') as line_key,
       store_domain, is_synthetic, source_id as sale_id,
       payload->>'__typename' as sale_type,
       payload->>'actionType' as action_type, payload->>'lineType' as line_type,
       (payload->>'quantity')::integer as quantity,
       (payload#>>'{totalAmount,shopMoney,amount}')::numeric as total_amount,
       (payload#>>'{totalTaxAmount,shopMoney,amount}')::numeric as tax_amount,
       (payload#>>'{totalDiscountAmountBeforeTaxes,shopMoney,amount}')::numeric as discount_before_tax,
       (payload#>>'{totalDiscountAmountAfterTaxes,shopMoney,amount}')::numeric as discount_after_tax,
       payload#>>'{totalAmount,shopMoney,currencyCode}' as currency_code,
       (payload#>>'{totalTaxAmount,shopMoney,currencyCode}' = payload#>>'{totalAmount,shopMoney,currencyCode}'
        and payload#>>'{totalDiscountAmountBeforeTaxes,shopMoney,currencyCode}' = payload#>>'{totalAmount,shopMoney,currencyCode}'
        and payload#>>'{totalDiscountAmountAfterTaxes,shopMoney,currencyCode}' = payload#>>'{totalAmount,shopMoney,currencyCode}') as currencies_match
from {{ source('shopify_raw', 'shopify_records') }}
where entity = 'sale'
