"""Fixed workflow: python -m pipeline.run. Exit 0 success, 1 failure, 2 busy."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from uuid import uuid4

from psycopg.rows import dict_row

from ingestion.client import ShopifyClient
from ingestion.config import ShopifyConfig
from ingestion.run import ingest
from ingestion.storage import Repository, connect
from pipeline import locking
from pipeline.publication import publish

ROOT = Path(__file__).resolve().parents[1]
ERRORS = {
    "ingestion": "Shopify ingestion failed. Check backend configuration, API access and ingestion audit status.",
    "dbt": "dbt build or tests failed. Candidate data was not published; operator review is required.",
    "publish": "Validated publication failed. The previous dashboard snapshot was retained.",
}


def initialize(connection):
    connection.execute(Path(__file__).with_name("schema.sql").read_text())
    connection.commit()


def recover_orphans(connection):
    # Caller must hold the advisory lock: no live supported worker can own rows.
    connection.execute("""UPDATE operations.pipeline_runs SET status='failed',finished_at=clock_timestamp(),
        duration_seconds=extract(epoch from clock_timestamp()-started_at),
        stages=stages || jsonb_build_array(jsonb_build_object('stage',stage,'status','failed',
            'timestamp',clock_timestamp())),
        error='Backend stopped before completion; no successful refresh was confirmed.' WHERE status='running'""")
    connection.commit()


def prepare(connection, origin="cli"):
    """Acquire before admitting a request; a different process uses the same lock."""
    if not locking.acquire(connection):
        return None
    try:
        recover_orphans(connection)
        run_id = uuid4()
        connection.execute("INSERT INTO operations.pipeline_runs (id,status,stage,origin) VALUES (%s,'running','ingestion',%s)", (run_id, origin))
        connection.commit()
        return run_id
    except Exception:
        locking.release(connection)
        raise


def stage(connection, run_id, name, state):
    connection.execute("""UPDATE operations.pipeline_runs SET stage=%s,
        stages=stages || jsonb_build_array(jsonb_build_object('stage',%s::text,'status',%s::text,
            'timestamp',clock_timestamp())) WHERE id=%s""", (name, name, state, run_id))
    connection.commit()


def ingest_shopify(connection):
    config = ShopifyConfig.from_env()
    repo = Repository(connection, config.store)
    repo.initialize()
    client = ShopifyClient(config)
    try:
        return ingest(client, repo, verify_order="#1001")
    finally:
        client.close()


def build_dbt():
    # Fixed argv, no shell, no user parameters. Private artifacts are temporary;
    # dbt output/exception text is never sent to the UI or stored in run errors.
    with tempfile.TemporaryDirectory(prefix="shopify-dbt-") as directory:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("SHOPIFY_", "PIPELINE_"))}
        result = subprocess.run(["dbt", "--warn-error", "build", "--project-dir", str(ROOT / "dbt"),
                                 "--profiles-dir", str(ROOT / "dbt"), "--target-path", directory + "/target",
                                 "--log-path", directory + "/logs"],
                                shell=False, timeout=900, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        if result.returncode != 0:
            raise RuntimeError("dbt validation failed")
        artifact = json.loads(Path(directory, "target", "run_results.json").read_text())
        if not artifact["results"] or any(r["status"] not in ("success", "pass") for r in artifact["results"]):
            raise RuntimeError("dbt results did not pass")


def execute(connection, run_id, ingestion=ingest_shopify, dbt=build_dbt, publication=publish):
    current = "ingestion"
    try:
        for current, action in (("ingestion", lambda: ingestion(connection)), ("dbt", dbt),
                                ("publish", lambda: publication(connection, run_id))):
            stage(connection, run_id, current, "running")
            action()
            if current != "publish":
                stage(connection, run_id, current, "succeeded")
        return {"status": "succeeded", "run_id": str(run_id)}
    except Exception:
        connection.rollback()
        connection.execute("""UPDATE operations.pipeline_runs SET status='failed',stage=%s,error=%s,
            finished_at=clock_timestamp(),duration_seconds=extract(epoch from clock_timestamp()-started_at),
            stages=stages || jsonb_build_array(jsonb_build_object('stage',%s::text,'status','failed',
                'timestamp',clock_timestamp())) WHERE id=%s""", (current, ERRORS[current], current, run_id))
        connection.commit()
        return {"status": "failed", "run_id": str(run_id), "error": ERRORS[current]}
    finally:
        locking.release(connection)


def status(connection):
    # A dead worker releases its session lock. Report an orphan as failed rather
    # than leaving the button permanently disabled after a backend restart.
    candidate = connection.execute("SELECT EXISTS (SELECT 1 FROM operations.pipeline_runs WHERE status='running')").fetchone()[0]
    connection.commit()
    if candidate and locking.acquire(connection):
        try:
            recover_orphans(connection)
        finally:
            locking.release(connection)
    with connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT id,status,stage,origin,started_at,finished_at,duration_seconds,stages,error FROM operations.pipeline_runs ORDER BY started_at DESC LIMIT 1")
            latest = cursor.fetchone()
            cursor.execute("SELECT run_id,published_at FROM reporting.publication WHERE singleton")
            publication = cursor.fetchone()
    return {"current": latest, "publication": publication}


def main():
    try:
        with connect() as connection:
            initialize(connection)
            run_id = prepare(connection)
            result = execute(connection, run_id) if run_id else {"status": "already_running"}
        print(json.dumps(result))
        return {"succeeded": 0, "failed": 1, "already_running": 2}[result["status"]]
    except Exception:
        print(json.dumps({"status": "failed", "error": "Pipeline database/setup failure; check backend health."}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
