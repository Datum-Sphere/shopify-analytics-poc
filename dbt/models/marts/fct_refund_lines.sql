-- Audit grain: one refund line source ID, independent of sales-event amounts.
select l.*, r.order_key, r.created_at as refund_created_at, r.processed_at as refund_processed_at,
       o.reporting_timezone,
       (coalesce(r.processed_at, r.created_at) at time zone o.reporting_timezone)::date as refund_date
from {{ ref('stg_refund_lines') }} l
join {{ ref('stg_refunds') }} r using (refund_key)
join {{ ref('stg_orders') }} o on r.order_key=o.order_key
