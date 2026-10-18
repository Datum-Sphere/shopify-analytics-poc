"""Real PostgreSQL/dashboard role checks; do not call or modify Shopify."""
import os
import unittest
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from dashboard import data
from ingestion.fixtures import load_records
from ingestion.storage import Repository, connect as admin_connect


@unittest.skipUnless(os.getenv("RUN_DASHBOARD_DB_TESTS")=="1","set RUN_DASHBOARD_DB_TESTS=1 after financial dbt build")
class DashboardDatabaseTests(unittest.TestCase):
    def reader(self):
        conn=psycopg.connect(host=os.environ["POSTGRES_HOST"],port=int(os.getenv("POSTGRES_PORT","5432")),
                              dbname=os.environ["POSTGRES_DB"],user="shopify_dashboard",
                              password=os.environ["DASHBOARD_DB_PASSWORD"],row_factory=dict_row,connect_timeout=5)
        conn.read_only=True
        conn.isolation_level=psycopg.IsolationLevel.REPEATABLE_READ
        return conn

    def test_live_order_1001_and_dataset_currency_isolation(self):
        live=data.load(data.Filters(False,"demo-analytics-poc.myshopify.com","CAD",date(2026,10,1),date(2026,10,31)),self.reader)
        self.assertEqual(live["status"],"ready")
        self.assertEqual(live["kpis"]["gross_sales"],Decimal(200))
        self.assertEqual(live["kpis"]["net_sales"],Decimal(200))
        fixture=data.load(data.Filters(True,"financial-fixtures.invalid","CAD",date(2026,10,1),date(2026,10,6)),self.reader)
        self.assertEqual([fixture["kpis"][k] for k in data.METRICS],[Decimal(340),Decimal(25),Decimal(180),Decimal(135)])
        self.assertEqual(sum(p["net_sales"] for p in fixture["products"]),Decimal(135))
        usd=data.load(data.Filters(True,"financial-fixtures.invalid","USD",date(2026,10,1),date(2026,10,6)),self.reader)
        self.assertEqual(usd["kpis"]["net_sales"],Decimal(7))
        wrong=data.load(data.Filters(False,"financial-fixtures.invalid","CAD",date(2026,10,1),date(2026,10,6)),self.reader)
        self.assertEqual(wrong["status"],"empty")

    def test_later_return_and_no_data_keep_sign_and_null(self):
        filters=data.Filters(True,"financial-fixtures.invalid","CAD",date(2026,10,4),date(2026,10,4))
        result=data.load(filters,self.reader)
        self.assertEqual(result["kpis"]["net_sales"],Decimal(-90))
        self.assertEqual(result["kpis"]["returns_amount"],Decimal(90))
        empty=data.load(data.Filters(True,filters.store,"CAD",date(2026,10,3),date(2026,10,3)),self.reader)
        self.assertEqual(empty["status"],"empty")
        self.assertIsNone(empty["kpis"]["net_sales"])

    def test_role_select_only_and_no_raw_access(self):
        with self.reader() as conn:
            flags=conn.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
            self.assertTrue(all(v is False for v in flags.values()))
            self.assertEqual(conn.execute("SHOW default_transaction_read_only").fetchone()["default_transaction_read_only"],"on")
            grants=conn.execute("SELECT table_name FROM information_schema.role_table_grants WHERE grantee=current_user AND table_schema='analytics'").fetchall()
            self.assertEqual({r["table_name"] for r in grants},{"mart_daily_sales","fct_sales_events","dim_product","dashboard_ingestion_status","dashboard_financial_issues"})
        for query in ("SELECT payload FROM raw.shopify_records LIMIT 1",
                      "UPDATE raw.shopify_records SET payload=payload WHERE false",
                      "SELECT error FROM raw.ingestion_runs LIMIT 1",
                      "CREATE TABLE public.dashboard_forbidden_test (id int)",
                      "CREATE TEMP TABLE dashboard_forbidden_test (id int)",
                      "SET ROLE shopify_app"):
            conn=self.reader()
            conn.read_only=False  # Prove ACLs, even if a client disables the convenience default.
            try:
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):conn.execute(query)
            finally:conn.rollback();conn.close()

    def test_custom_product_and_unsupported_quality_scope(self):
        store="dashboard-fixture-"+uuid4().hex+".invalid"
        with admin_connect() as admin:
            repo=Repository(admin,store,is_synthetic=True)
            repo.initialize()
            try:
                load_records(repo)
                admin.execute("UPDATE raw.shopify_records SET payload=jsonb_set(payload,'{product}','null') WHERE store_domain=%s AND entity='order_line_item' AND source_id LIKE '%%A1'",(store,))
                admin.commit()
                full=data.load(data.Filters(True,store,"CAD",date(2026,10,1),date(2026,10,6)),self.reader)
                custom=[p for p in full["products"] if p["title"]=="Custom / unlinked product"]
                self.assertEqual(len(custom),1)
                self.assertEqual(sum(p["net_sales"] for p in full["products"]),Decimal(135))
                admin.execute("UPDATE raw.shopify_records SET payload=jsonb_set(payload,'{actionType}',%s::jsonb) WHERE store_domain=%s AND entity='sale' AND source_id LIKE '%%return-1' AND payload->>'lineType'='PRODUCT'",('"UPDATE"',store))
                admin.commit()
                blocked=data.load(data.Filters(True,store,"CAD",date(2026,10,4),date(2026,10,4)),self.reader)
                self.assertEqual(blocked["status"],"unsupported")
                self.assertIsNone(blocked["kpis"]["net_sales"])
                self.assertEqual(blocked["products"],[])
                other_date=data.load(data.Filters(True,store,"CAD",date(2026,10,1),date(2026,10,1)),self.reader)
                self.assertEqual(other_date["status"],"ready")
                other_currency=data.load(data.Filters(True,store,"USD",date(2026,10,4),date(2026,10,4)),self.reader)
                self.assertEqual(other_currency["status"],"empty")
                # A non-product adjustment is absent from the mart but must still block reporting.
                admin.execute("UPDATE raw.shopify_records SET payload=jsonb_set(payload,'{actionType}',%s::jsonb) WHERE store_domain=%s AND entity='sale' AND source_id LIKE '%%return-1' AND payload->>'lineType'='PRODUCT'",('"RETURN"',store))
                admin.execute("UPDATE raw.shopify_records SET payload=jsonb_set(payload,'{__typename}',%s::jsonb) WHERE store_domain=%s AND entity='sale' AND payload->>'lineType'='SHIPPING'",('"AdjustmentSale"',store))
                admin.commit()
                adjustment=data.load(data.Filters(True,store,"CAD",date(2026,10,4),date(2026,10,4)),self.reader)
                self.assertEqual(adjustment["status"],"unsupported")
                self.assertGreater(adjustment["issue_count"],0)
                # Unknown-date extraction gaps block even an otherwise valid earlier day.
                admin.execute("UPDATE raw.shopify_records SET payload=payload-'agreements' WHERE store_domain=%s AND entity='order' AND payload->>'name'='#FIXTURE-B'",(store,))
                admin.commit()
                gap=data.load(data.Filters(True,store,"CAD",date(2026,10,1),date(2026,10,1)),self.reader)
                self.assertEqual(gap["status"],"unsupported")
                self.assertIsNone(gap["kpis"]["gross_sales"])
            finally:
                admin.rollback()
                for table in ("shopify_records","ingestion_runs"):
                    admin.execute("DELETE FROM raw."+table+" WHERE store_domain=%s",(store,))
                admin.commit()
