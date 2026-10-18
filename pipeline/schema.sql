CREATE SCHEMA IF NOT EXISTS operations;
CREATE TABLE IF NOT EXISTS operations.pipeline_runs (
    id uuid PRIMARY KEY,
    status text NOT NULL CHECK (status IN ('running','succeeded','failed')),
    stage text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    duration_seconds double precision,
    stages jsonb NOT NULL DEFAULT '[]',
    error text
);
ALTER TABLE operations.pipeline_runs ADD COLUMN IF NOT EXISTS origin text NOT NULL DEFAULT 'cli'
    CHECK (origin IN ('cli','dashboard','test'));
CREATE SCHEMA IF NOT EXISTS reporting;
CREATE TABLE IF NOT EXISTS reporting.publication (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    run_id uuid NOT NULL,
    published_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
