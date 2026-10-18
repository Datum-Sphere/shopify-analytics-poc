"""Real PostgreSQL locks/publication and real dbt failure; Shopify is mocked."""
import os
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg

from ingestion.fixtures import load_records
from ingestion.storage import Repository, connect
from pipeline import api, locking, run
from pipeline.publication import MODELS, publish


@unittest.skipUnless(os.getenv("RUN_PIPELINE_DB_TESTS")=="1","set RUN_PIPELINE_DB_TESTS=1 after first successful pipeline")
class PipelineDatabaseTests(unittest.TestCase):
    def snapshot(self):
        with connect() as conn:
            return {name:conn.execute("SELECT to_jsonb(t)::text FROM reporting."+name+" t ORDER BY 1").fetchall()
                    for name in (*MODELS,"publication")}

    def test_advisory_lock_across_connections_and_busy_audit(self):
        with connect() as owner,connect() as other:
            self.assertTrue(locking.acquire(owner))
            self.assertIsNone(run.prepare(other,origin="test"))
            self.assertFalse(locking.acquire(other))
            busy=subprocess.run([sys.executable,"-m","pipeline.run"],capture_output=True,text=True,timeout=15)
            self.assertEqual(busy.returncode,2)
            self.assertIn("already_running",busy.stdout)
            locking.release(owner)
            self.assertTrue(locking.acquire(other))
            locking.release(other)

    def test_concurrent_backend_requests_admit_one_worker(self):
        entered=threading.Event()
        finish=threading.Event()
        original=run.execute
        def paused(conn,run_id):
            entered.set()
            finish.wait(10)
            # Failure is deliberate: this test must not publish mocked data.
            return original(conn,run_id,ingestion=lambda c:(_ for _ in ()).throw(RuntimeError("test failure")))
        try:
            with patch("pipeline.api.execute",side_effect=paused),patch("pipeline.api.prepare",side_effect=lambda c,origin:run.prepare(c,origin="test")):
                first=api.start()
                self.assertIsNotNone(first)
                self.assertTrue(entered.wait(5))
                self.assertIsNone(api.start())
                self.assertIsNone(api.start())
                finish.set()
                # Wait on the lock, bounded by the test worker's completion.
                for thread in threading.enumerate():
                    if thread.name=="pipeline-worker":thread.join(10)
        finally:
            finish.set()

    def test_failed_real_dbt_validation_preserves_every_published_table(self):
        before=self.snapshot()
        store="failed-pipeline-"+uuid4().hex+".invalid"
        with connect() as conn:
            run_id=run.prepare(conn,origin="test")
            self.assertIsNotNone(run_id)
            def invalid_ingestion(connection):
                repo=Repository(connection,store,is_synthetic=True)
                load_records(repo)
                connection.execute("UPDATE raw.shopify_records SET payload=jsonb_set(payload,'{actionType}','\"UPDATE\"') WHERE store_domain=%s AND entity='sale' AND payload->>'lineType'='PRODUCT'",(store,))
                connection.commit()
            try:
                result=run.execute(conn,run_id,ingestion=invalid_ingestion)
                self.assertEqual(result["status"],"failed")
                row=conn.execute("SELECT stage,status,error FROM operations.pipeline_runs WHERE id=%s",(run_id,)).fetchone()
                conn.commit()
                self.assertEqual(row[:2],("dbt","failed"))
                self.assertEqual(self.snapshot(),before)
                self.assertGreater(conn.execute("SELECT count(*) FROM raw.shopify_records WHERE store_domain=%s",(store,)).fetchone()[0],0)
            finally:
                conn.rollback()
                conn.execute("DELETE FROM raw.shopify_records WHERE store_domain=%s",(store,))
                conn.execute("DELETE FROM raw.ingestion_runs WHERE store_domain=%s",(store,))
                conn.commit()

    def test_publication_failure_rolls_back_and_replay_preserves_amounts(self):
        before=self.snapshot()
        with connect() as conn:
            run_id=run.prepare(conn,origin="test")
            class Broken:
                transaction=conn.transaction
                def execute(self,query,params=None):
                    text=query if isinstance(query,str) else query.as_string(conn)
                    if text.startswith('INSERT INTO "reporting".'):
                        raise RuntimeError("secret-must-not-escape")
                    return conn.execute(query,params)
            def fail_publication(c,r):publish(Broken(),r)
            result=run.execute(conn,run_id,ingestion=lambda c:None,dbt=lambda:None,publication=fail_publication)
            self.assertEqual(result["status"],"failed")
            self.assertEqual(self.snapshot(),before)
            # Replaying identical validated model data replaces rows, never appends.
            with psycopg.connect(host=os.environ["POSTGRES_HOST"],port=int(os.getenv("POSTGRES_PORT","5432")),
                                 dbname=os.environ["POSTGRES_DB"],user="shopify_dashboard",
                                 password=os.environ["DASHBOARD_DB_PASSWORD"],connect_timeout=5) as reader:
                reader.read_only=True
                reader.isolation_level=psycopg.IsolationLevel.REPEATABLE_READ
                old=reader.execute("SELECT run_id FROM reporting.publication").fetchone()[0]
                for _ in range(2):
                    run_id=run.prepare(conn,origin="test")
                    result=run.execute(conn,run_id,ingestion=lambda c:None,dbt=run.build_dbt)
                    self.assertEqual(result["status"],"succeeded")
                    after=self.snapshot()
                    self.assertEqual({k:v for k,v in before.items() if k!="publication"},
                                     {k:v for k,v in after.items() if k!="publication"})
                    self.assertEqual(reader.execute("SELECT run_id FROM reporting.publication").fetchone()[0],old)
                    # First read of this table occurs AFTER publication: old row
                    # versions must still exist, not disappear as with TRUNCATE.
                    self.assertGreater(reader.execute("SELECT count(*) FROM reporting.mart_daily_sales").fetchone()[0],0)

    def test_orphaned_run_is_failed_and_lock_released_on_disconnect(self):
        conn=connect()
        run_id=run.prepare(conn,origin="test")
        self.assertIsNotNone(run_id)
        conn.close()  # simulate process loss; session advisory lock disappears
        with connect() as reader:
            state=run.status(reader)
        self.assertEqual(str(state["current"]["id"]),str(run_id))
        self.assertEqual(state["current"]["status"],"failed")
