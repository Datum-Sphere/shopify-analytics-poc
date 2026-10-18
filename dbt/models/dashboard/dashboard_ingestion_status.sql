-- Safe metadata only: never expose raw run errors, payloads, or credentials.
select store_domain, store_domain like '%.invalid' as is_synthetic,
       max(finished_at) as last_successful_ingestion_at
from {{ source('shopify_raw', 'ingestion_runs') }}
where status='succeeded'
group by store_domain
