"""Opt-in real PostgreSQL tests with mocked Shopify extraction, never live Shopify."""
import os
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from ingestion.config import IngestionError
from ingestion.run import ingest
from ingestion.storage import Repository, connect


@unittest.skipUnless(os.getenv("RUN_DB_TESTS") == "1", "set RUN_DB_TESTS=1 for real PostgreSQL smoke tests")
class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.connection = connect()
        self.store = "fixture-" + uuid4().hex + ".myshopify.com"
        self.repo = Repository(self.connection, self.store)
        self.repo.initialize()

    def tearDown(self):
        self.connection.rollback()
        for table in ("shopify_records", "ingestion_runs"):
            self.connection.execute("DELETE FROM raw." + table + " WHERE store_domain=%s", (self.store,))
        self.connection.commit()
        self.connection.close()

    def test_duplicate_upsert_and_payload_update(self):
        with patch("ingestion.run.products", return_value=[{"id": "fixture-product", "title": "Before", "variants": []}]), patch("ingestion.run.orders", return_value=[]):
            ingest(Mock(), self.repo)
        with patch("ingestion.run.products", return_value=[{"id": "fixture-product", "title": "After", "variants": []}]), patch("ingestion.run.orders", return_value=[]):
            result = ingest(Mock(), self.repo)
        self.assertEqual(result["unique_records"]["product"], 1)
        title = self.connection.execute("SELECT payload->>'title' FROM raw.shopify_records WHERE store_domain=%s", (self.store,)).fetchone()[0]
        self.assertEqual(title, "After")

    def test_failed_run_rolls_back_records_but_keeps_audit(self):
        def broken_products(_):
            yield {"id": "fixture-product", "variants": []}
            raise RuntimeError("sensitive sentinel")
        with patch("ingestion.run.products", broken_products), self.assertRaises(IngestionError):
            ingest(Mock(), self.repo)
        self.assertEqual(sum(self.repo.counts().values()), 0)
        status, error = self.connection.execute("SELECT status, error FROM raw.ingestion_runs WHERE store_domain=%s", (self.store,)).fetchone()
        self.assertEqual(status, "failed")
        self.assertNotIn("sensitive sentinel", error)
