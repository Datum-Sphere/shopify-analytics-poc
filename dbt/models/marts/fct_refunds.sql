-- Aggregate children before joining headers; payment totals are audit-only.
with items as (
 select refund_key, count(*) as refund_line_count, sum(line_subtotal) as merchandise_refund_subtotal,
        sum(line_tax) as merchandise_refund_tax
 from {{ ref('stg_refund_lines') }} group by refund_key
)
select r.*, coalesce(i.refund_line_count, 0) as refund_line_count,
       coalesce(i.merchandise_refund_subtotal, 0) as merchandise_refund_subtotal,
       coalesce(i.merchandise_refund_tax, 0) as merchandise_refund_tax,
       r.payment_refunded_amount - coalesce(i.merchandise_refund_subtotal, 0)
         - coalesce(i.merchandise_refund_tax, 0) as payment_less_merchandise_and_tax
from {{ ref('stg_refunds') }} r left join items i using (refund_key)
