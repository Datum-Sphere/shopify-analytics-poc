"""Mocked HTTP tests. No developer-store traffic or credentials are used."""
import copy
import unittest
from unittest.mock import Mock, patch

import requests

from ingestion.client import ShopifyClient
from ingestion.config import IngestionError, ShopifyConfig
from ingestion.run import ingest
from ingestion.storage import Repository


def response(body, status=200, headers=None):
    result = Mock(status_code=status, headers=headers or {})
    result.json.return_value = body
    return result


def page(nodes, more=False, cursor=None):
    return {"nodes": nodes, "pageInfo": {"hasNextPage": more, "endCursor": cursor}}


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.sleep = Mock()
        self.clock = Mock(return_value=0)
        self.config = ShopifyConfig("unit-test.myshopify.com", "fake-client-id", "fake-secret")
        self.client = ShopifyClient(self.config, self.session, self.sleep, self.clock)
        self.token = response({"access_token": "fake-token", "expires_in": 120})

    def test_token_cached_then_refreshed_before_expiry(self):
        self.session.post.return_value = self.token
        self.assertEqual(self.client.token(), "fake-token")
        self.clock.return_value = 100
        self.client.token()
        self.assertEqual(self.session.post.call_count, 1)
        self.clock.return_value = 109
        self.client.token()
        self.assertEqual(self.session.post.call_count, 2)
        args = self.session.post.call_args.kwargs
        self.assertEqual(args["data"]["grant_type"], "client_credentials")
        self.assertEqual(args["timeout"], (10, 60))
        self.assertFalse(args["allow_redirects"])
        self.assertNotIn("fake-secret", repr(self.config))

    def test_authentication_errors_are_redacted(self):
        self.session.post.return_value = response({"error": "fake-secret fake-token"}, 401)
        with self.assertRaises(IngestionError) as caught:
            self.client.token()
        self.assertNotIn("fake-secret", str(caught.exception))
        self.assertNotIn("fake-token", str(caught.exception))

    def test_invalid_expiry_is_rejected(self):
        self.session.post.return_value = response({"access_token": "fake-token", "expires_in": 0})
        with self.assertRaisesRegex(IngestionError, "invalid token"):
            self.client.token()

    def test_http_retry_and_retry_after(self):
        self.session.post.side_effect = [response({}, 429, {"Retry-After": "3"}), self.token]
        self.client.token()
        self.assertGreaterEqual(self.sleep.call_args.args[0], 3)
        self.assertEqual(self.session.post.call_count, 2)

    def test_timeout_retry_budget_is_bounded_and_redacted(self):
        self.session.post.side_effect = requests.Timeout("fake-secret")
        with self.assertRaisesRegex(IngestionError, "4 attempts") as caught:
            self.client.token()
        self.assertNotIn("fake-secret", str(caught.exception))
        self.assertEqual(self.session.post.call_count, 4)
        self.assertEqual(self.sleep.call_count, 3)

    def test_graphql_throttling_then_success(self):
        self.session.post.side_effect = [self.token,
            response({"errors": [{"extensions": {"code": "THROTTLED"}}]}),
            response({"data": {"ok": True}})]
        self.assertEqual(self.client.graphql("query Test { shop { id } }"), {"ok": True})
        self.sleep.assert_called_once()

    def test_expired_token_401_refreshes_once(self):
        self.session.post.side_effect = [self.token, response({}, 401), self.token,
                                         response({"data": {"ok": True}})]
        self.assertEqual(self.client.graphql("query Test { shop { id } }"), {"ok": True})
        self.assertEqual(self.session.post.call_count, 4)

    def test_graphql_partial_data_and_errors_are_rejected(self):
        self.session.post.side_effect = [self.token, response({"data": {"ok": True},
            "errors": [{"message": "fake-secret", "extensions": {"code": "ACCESS_DENIED"}}]})]
        with self.assertRaisesRegex(IngestionError, "access denied") as caught:
            self.client.graphql("query Test { shop { id } }")
        self.assertNotIn("fake-secret", str(caught.exception))

    def test_version_fallback_is_rejected(self):
        self.session.post.side_effect = [self.token, response({"data": {}}, headers={"X-Shopify-API-Version": "2026-07"})]
        with self.assertRaisesRegex(IngestionError, "version differs"):
            self.client.graphql("query Test { shop { id } }")

    def test_non_json_and_mutations_rejected(self):
        bad = response({})
        bad.json.side_effect = ValueError("fake-secret")
        self.session.post.side_effect = [self.token, bad]
        with self.assertRaisesRegex(IngestionError, "invalid JSON"):
            self.client.graphql("query Test { shop { id } }")
        with self.assertRaisesRegex(IngestionError, "read-only"):
            self.client.graphql("mutation Delete { productDelete { id } }")

    def test_cursor_pagination(self):
        self.session.post.side_effect = [self.token,
            response({"data": {"products": page([{"id": "1"}], True, "cursor-1")}}),
            response({"data": {"products": page([{"id": "2"}])}})]
        rows = list(self.client.paginate("query Products($after: String) { products { id } }", ("products",)))
        self.assertEqual([row["id"] for row in rows], ["1", "2"])
        self.assertEqual(self.session.post.call_args.kwargs["json"]["variables"]["after"], "cursor-1")

    def test_nested_line_item_pagination(self):
        self.session.post.side_effect = [self.token,
            response({"data": {"order": {"lineItems": page([{"id": "line-1"}], True, "cursor-1")}}}),
            response({"data": {"order": {"lineItems": page([{"id": "line-2"}])}}})]
        rows = list(self.client.paginate("query Lines($id: ID!, $after: String) { order { id } }", ("order", "lineItems"), {"id": "fixture-order"}))
        self.assertEqual(len(rows), 2)
        self.assertEqual(self.session.post.call_args.kwargs["json"]["variables"], {"id": "fixture-order", "after": "cursor-1"})

    def test_repeated_cursor_fails(self):
        self.client.graphql = Mock(return_value={"products": page([], True, "same")})
        with self.assertRaisesRegex(IngestionError, "cursor"):
            list(self.client.paginate("query Products { products { id } }", ("products",)))


PRODUCT = {"id": "gid://shopify/Product/1", "title": "Fixture", "variants": [{"id": "gid://shopify/ProductVariant/1", "price": "10.00"}]}
ORDER = {"id": "gid://shopify/Order/1", "name": "#1001", "test": True,
         "lineItems": [{"id": "gid://shopify/LineItem/1", "quantity": 1}],
         "discountApplications": [], "transactions": [{"id": "gid://shopify/OrderTransaction/1", "status": "SUCCESS"}]}


class MemoryRepository:
    def __init__(self):
        self.records = {}
        self.runs = []
        self.connection = Mock()

    def start(self):
        return len(self.runs) + 1

    def upsert(self, entity, payload, parent_id=None):
        self.records[(entity, payload["id"])] = copy.deepcopy(payload)

    def finish(self, *args, **kwargs):
        self.runs.append((args, kwargs))

    def counts(self):
        from ingestion.storage import ENTITIES
        return {entity: sum(key[0] == entity for key in self.records) for entity in ENTITIES}


class RunTests(unittest.TestCase):
    @patch("ingestion.run.orders", return_value=[ORDER])
    @patch("ingestion.run.products", return_value=[PRODUCT])
    def test_duplicate_ingestion_updates_without_inserting(self, products_mock, orders_mock):
        repo = MemoryRepository()
        client = Mock()
        client.paginate.return_value = [ORDER]
        first = ingest(client, repo, "#1001")
        second = ingest(client, repo, "#1001")
        self.assertEqual(first["unique_records"], second["unique_records"])
        self.assertEqual(sum(second["unique_records"].values()), 5)
        self.assertEqual(second["verified_order"], "#1001")
        self.assertEqual(len(repo.runs), 2)

    @patch("ingestion.run.products", side_effect=RuntimeError("fake-secret"))
    def test_failure_recorded_without_sensitive_exception(self, _):
        repo = MemoryRepository()
        with self.assertRaises(IngestionError) as caught:
            ingest(Mock(), repo)
        self.assertNotIn("fake-secret", str(caught.exception))
        repo.connection.rollback.assert_called_once()
        self.assertEqual(repo.runs[0][0][1], "failed")
        self.assertEqual(repo.runs[0][0][2], {})

    def test_verification_requires_exact_order_name(self):
        client = Mock()
        client.paginate.return_value = [{"id": "fixture-order", "name": "#10010", "test": True}]
        with self.assertRaisesRegex(IngestionError, "not accessible"):
            ingest(client, MemoryRepository(), "#1001")

    def test_upsert_uses_source_key_and_jsonb_parameters(self):
        conn = Mock()
        Repository(conn, "unit-test.myshopify.com").upsert("product", PRODUCT)
        sql, params = conn.execute.call_args.args
        self.assertIn("ON CONFLICT (store_domain, entity, source_id) DO UPDATE", sql)
        self.assertEqual(params[:3], ("unit-test.myshopify.com", "product", PRODUCT["id"]))


if __name__ == "__main__":
    unittest.main()
