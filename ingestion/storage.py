"""PostgreSQL JSONB persistence. No token, customer or credential tables."""
import os
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

ENTITIES = ("product", "variant", "order", "order_line_item", "order_transaction")


def connect():
    return psycopg.connect(host=os.environ["POSTGRES_HOST"],
                           port=int(os.getenv("POSTGRES_PORT", "5432")),
                           dbname=os.environ["POSTGRES_DB"], user=os.environ["POSTGRES_USER"],
                           password=os.environ["DBT_ENV_SECRET_POSTGRES_PASSWORD"], connect_timeout=5)


class Repository:
    def __init__(self, connection, store):
        self.connection = connection
        self.store = store

    def initialize(self):
        self.connection.execute(Path(__file__).with_name("schema.sql").read_text())
        self.connection.commit()

    def start(self):
        row = self.connection.execute(
            "INSERT INTO raw.ingestion_runs (store_domain) VALUES (%s) RETURNING id", (self.store,)
        ).fetchone()
        self.connection.commit()
        return row[0]

    def upsert(self, entity, payload, parent_id=None):
        if entity not in ENTITIES:
            raise ValueError("Unknown record entity")
        self.connection.execute("""
            INSERT INTO raw.shopify_records (store_domain, entity, source_id, parent_source_id, payload)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (store_domain, entity, source_id) DO UPDATE SET
                parent_source_id = EXCLUDED.parent_source_id,
                payload = EXCLUDED.payload, ingested_at = now()
        """, (self.store, entity, payload["id"], parent_id, Jsonb(payload)))

    def finish(self, run_id, status, counts, error=None, verified_order=None):
        self.connection.execute("""
            UPDATE raw.ingestion_runs SET status=%s, finished_at=clock_timestamp(),
                row_counts=%s, error=%s, verified_order=%s WHERE id=%s
        """, (status, Jsonb(counts), error, verified_order, run_id))
        self.connection.commit()

    def counts(self):
        rows = self.connection.execute("""
            SELECT entity, count(*) FROM raw.shopify_records WHERE store_domain=%s GROUP BY entity
        """, (self.store,)).fetchall()
        return {entity: dict(rows).get(entity, 0) for entity in ENTITIES}
