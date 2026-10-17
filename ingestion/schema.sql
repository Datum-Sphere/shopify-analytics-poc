CREATE SCHEMA IF NOT EXISTS raw;
CREATE TABLE IF NOT EXISTS raw.shopify_records (
    store_domain text NOT NULL,
    entity text NOT NULL CHECK (entity IN ('product', 'variant', 'order', 'order_line_item', 'order_transaction')),
    source_id text NOT NULL,
    parent_source_id text,
    payload jsonb NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (store_domain, entity, source_id)
);
CREATE TABLE IF NOT EXISTS raw.ingestion_runs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    store_domain text NOT NULL,
    status text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'succeeded', 'failed')),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    row_counts jsonb NOT NULL DEFAULT '{}'::jsonb,
    error text,
    verified_order text
);

-- Small, repeatable migration from Phase 2; retain every existing source row.
ALTER TABLE raw.shopify_records ADD COLUMN IF NOT EXISTS is_synthetic boolean NOT NULL DEFAULT false;
ALTER TABLE raw.shopify_records DROP CONSTRAINT IF EXISTS shopify_records_entity_check;
ALTER TABLE raw.shopify_records ADD CONSTRAINT shopify_records_entity_check CHECK
 (entity IN ('product','variant','order','order_line_item','order_transaction',
             'refund','refund_line_item','sales_agreement','sale'));
