"""Refund/agreement extraction tests; fixture scenarios are not Shopify report captures."""
import copy
import os
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from ingestion.config import IngestionError
from ingestion.extract import agreements, orders
from ingestion.fixtures import load_records
from ingestion.run import ingest
from ingestion.storage import Repository, connect
from test_ingestion import ORDER, PRODUCT, MemoryRepository, page


def agreement_page(agreement_id, sales, more_sales=False, sales_cursor=None, more_agreements=False, agreement_cursor=None):
    return {"order": {"agreements": page([{"id": agreement_id, "sales": page(sales,more_sales,sales_cursor)}],more_agreements,agreement_cursor)}}


class FinancialExtractionTests(unittest.TestCase):
    def test_nested_agreement_sales_pages_keep_outer_cursor(self):
        client=Mock()
        client.graphql.side_effect=[
            agreement_page("a1",[{"id":"s1"}],True,"s1",True,"a1"),
            agreement_page("a1",[{"id":"s2"}]),
            agreement_page("a2",[{"id":"s3"}])]
        result=list(agreements(client,"o1"))
        self.assertEqual([[s["id"] for s in a["sales"]] for a in result],[["s1","s2"],["s3"]])
        self.assertEqual(client.graphql.call_args_list[1].args[1]["after"],None)
        self.assertEqual(client.graphql.call_args_list[1].args[1]["salesAfter"],"s1")
        self.assertEqual(client.graphql.call_args_list[2].args[1]["after"],"a1")

    def test_changed_agreement_and_repeated_cursor_fail(self):
        client=Mock()
        client.graphql.side_effect=[agreement_page("a1",[],True,"same"),agreement_page("a2",[])]
        with self.assertRaisesRegex(IngestionError,"source changed"):
            list(agreements(client,"o1"))
        client.graphql.side_effect=None
        client.graphql.return_value=agreement_page("a1",[],True,"same")
        with self.assertRaisesRegex(IngestionError,"non-advancing"):
            list(agreements(client,"o1"))

    @patch("ingestion.extract.agreements",return_value=[])
    def test_refund_lines_and_adjustments_extracted(self,_):
        client=Mock()
        client.graphql.side_effect=[{"shop":{"ianaTimezone":"UTC"}},{"order":{"transactions":[]}},
                                   {"order":{"refunds":[{"id":"r1"}]}}]
        client.paginate.side_effect=[[{"id":"o1"}],[],[],[{"id":"rl1","lineItem":{"id":"l1"}}],[{"id":"adj1"}]]
        result=list(orders(client))[0]
        self.assertEqual(result["refunds"][0]["refundLineItems"][0]["id"],"rl1")
        self.assertEqual(result["refunds"][0]["orderAdjustments"][0]["id"],"adj1")
        self.assertEqual(result["_shop"]["ianaTimezone"],"UTC")

    @patch("ingestion.extract.agreements",return_value=[])
    def test_missing_refund_line_source_id_is_rejected(self,_):
        client=Mock()
        client.graphql.side_effect=[{"shop":{}},{"order":{"transactions":[]}},
                                   {"order":{"refunds":[{"id":"r1"}]}}]
        client.paginate.side_effect=[[{"id":"o1"}],[],[],[{"id":None}],[]]
        with self.assertRaisesRegex(IngestionError,"missing source refund-line ID"):
            list(orders(client))

    @patch("ingestion.run.orders")
    @patch("ingestion.run.products",return_value=[PRODUCT])
    def test_financial_entities_upsert_twice(self,_,mock_orders):
        o=copy.deepcopy(ORDER)
        o["refunds"]=[{"id":"r1","refundLineItems":[{"id":"rl1"}]}]
        o["agreements"]=[{"id":"a1","sales":[{"id":"s1"}]}]
        mock_orders.return_value=[o]
        repo=MemoryRepository()
        a=ingest(Mock(),repo)
        b=ingest(Mock(),repo)
        self.assertEqual(a["unique_records"],b["unique_records"])
        self.assertEqual(sum(b["unique_records"].values()),9)
        self.assertEqual(repo.records[("refund_line_item","rl1")]["id"],"rl1")


@unittest.skipUnless(os.getenv("RUN_DB_TESTS")=="1","set RUN_DB_TESTS=1 for PostgreSQL fixture replay")
class FinancialFixtureDatabaseTests(unittest.TestCase):
    def test_fixture_replay_uses_upserts(self):
        store="fixture-"+uuid4().hex+".invalid"
        with connect() as conn:
            repo=Repository(conn,store,is_synthetic=True)
            repo.initialize()
            try:
                first=load_records(repo)
                second=load_records(repo)
                self.assertEqual(first["unique_records"],second["unique_records"])
                self.assertEqual(second["unique_records"]["refund_line_item"],2)
                self.assertEqual(second["unique_records"]["sale"],8)
                self.assertEqual(conn.execute("SELECT bool_and(is_synthetic) FROM raw.shopify_records WHERE store_domain=%s",(store,)).fetchone()[0],True)
            finally:
                conn.rollback()
                for table in ("shopify_records","ingestion_runs"):
                    conn.execute("DELETE FROM raw."+table+" WHERE store_domain=%s",(store,))
                conn.commit()
