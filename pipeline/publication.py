"""Publish validated dbt output atomically; never expose mutable candidate views."""
from psycopg import sql

MODELS = ("mart_daily_sales", "fct_sales_events", "dim_product",
          "dashboard_ingestion_status", "dashboard_financial_issues")


def publish(connection, run_id):
    # Caller owns the pipeline lock and has completed dbt build. DELETE/INSERT,
    # rather than TRUNCATE, preserves old versions for repeatable-read readers.
    with connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        if connection.execute("SELECT count(*) FROM analytics.dashboard_financial_issues").fetchone()[0]:
            raise ValueError("Financial coverage checks failed")
        for name in MODELS:
            source = sql.Identifier("analytics", name)
            target = sql.Identifier("reporting", name)
            connection.execute(sql.SQL("CREATE TABLE IF NOT EXISTS {} AS SELECT * FROM {} WITH NO DATA").format(target, source))
            connection.execute(sql.SQL("DELETE FROM {}").format(target))
            connection.execute(sql.SQL("INSERT INTO {} SELECT * FROM {}").format(target, source))
            connection.execute(sql.SQL("GRANT SELECT ON {} TO shopify_dashboard").format(target))
        connection.execute("""INSERT INTO reporting.publication (singleton,run_id) VALUES (true,%s)
            ON CONFLICT (singleton) DO UPDATE SET run_id=excluded.run_id,published_at=clock_timestamp()""", (run_id,))
        # Publication and successful run state share a commit boundary.
        connection.execute("""UPDATE operations.pipeline_runs SET status='succeeded',stage='complete',
            finished_at=clock_timestamp(),duration_seconds=extract(epoch from clock_timestamp()-started_at),
            stages=stages || jsonb_build_array(jsonb_build_object('stage','publish','status','succeeded',
                'timestamp',clock_timestamp())) WHERE id=%s""", (run_id,))
