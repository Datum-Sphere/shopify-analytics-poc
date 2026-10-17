select s.sale_key as failing_key
from {{ ref('stg_sales') }} s
join {{ ref('stg_sales_agreements') }} a using (agreement_key)
join {{ ref('stg_order_lines') }} l on s.line_key=l.line_key
where a.order_key<>l.order_key or s.is_synthetic<>l.is_synthetic
union all
select rl.refund_line_key
from {{ ref('stg_refund_lines') }} rl
join {{ ref('stg_refunds') }} r using (refund_key)
join {{ ref('stg_order_lines') }} l using (line_key)
where r.order_key<>l.order_key or rl.is_synthetic<>l.is_synthetic
