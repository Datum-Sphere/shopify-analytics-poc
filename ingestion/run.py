"""CLI: python -m ingestion.run [--verify-order '#1001']. Never prints raw records."""
import argparse
import json

from ingestion.client import ShopifyClient
from ingestion.config import IngestionError, ShopifyConfig
from ingestion.extract import products, orders
from ingestion.queries import ORDERS
from ingestion.storage import ENTITIES, Repository, connect
from pipeline import locking


def ingest(client, repository, verify_order=None):
    run_id = repository.start()
    counts = dict.fromkeys(ENTITIES, 0)
    verified = None
    verified_test = None
    try:
        if verify_order:
            matches = list(client.paginate(ORDERS,
                                          ("orders",), {"search": "name:" + verify_order}))
            match = next((o for o in matches if o["name"] == verify_order), None)
            if match is None:
                raise IngestionError("verification: requested order not accessible; check its name and 60-day order visibility")
            verified = match["id"]
            verified_test = match.get("test")
        found_verified = not verify_order
        for product in products(client):
            repository.upsert("product", product)
            counts["product"] += 1
            for variant in product["variants"]:
                repository.upsert("variant", variant, product["id"])
                counts["variant"] += 1
        for order in orders(client):
            repository.upsert("order", order)
            counts["order"] += 1
            if order["id"] == verified:
                found_verified = True
            for field, entity in (("lineItems", "order_line_item"), ("transactions", "order_transaction")):
                for record in order[field]:
                    repository.upsert(entity, record, order["id"])
                    counts[entity] += 1
            for refund in order.get("refunds", []):
                repository.upsert("refund", refund, order["id"])
                counts["refund"] += 1
                for item in refund["refundLineItems"]:
                    repository.upsert("refund_line_item", item, refund["id"])
                    counts["refund_line_item"] += 1
            for agreement in order.get("agreements", []):
                repository.upsert("sales_agreement", agreement, order["id"])
                counts["sales_agreement"] += 1
                for sale in agreement["sales"]:
                    repository.upsert("sale", sale, agreement["id"])
                    counts["sale"] += 1
        if not found_verified:
            raise IngestionError("verification: requested order disappeared during extraction; retry the run")
        unique_counts = repository.counts()
        repository.finish(run_id, "succeeded", counts, verified_order=verify_order)
        return {"run_id": run_id, "status": "succeeded", "processed": counts,
                "unique_records": unique_counts, "verified_order": verify_order, "verified_order_test": verified_test}
    except Exception as exc:
        repository.connection.rollback()
        # Never persist exception text from requests, psycopg, or arbitrary input.
        message = str(exc) if isinstance(exc, IngestionError) else "ingestion: unexpected extraction/database failure"
        repository.finish(run_id, "failed", {}, message)
        raise IngestionError(message) from None


def main():
    parser = argparse.ArgumentParser(description="Read-only Shopify products and orders ingestion")
    parser.add_argument("--verify-order", help="Require an exact accessible order name, for example #1001")
    args = parser.parse_args()
    client = None
    try:
        config = ShopifyConfig.from_env()
        with connect() as connection:
            if not locking.acquire(connection):
                print('{"status":"already_running"}')
                return 2
            repo = Repository(connection, config.store)
            repo.initialize()
            client = ShopifyClient(config)
            print(json.dumps(ingest(client, repo, args.verify_order), sort_keys=True))
    except Exception as exc:
        message = str(exc) if isinstance(exc, IngestionError) else "ingestion: database/configuration failure; check container environment and PostgreSQL health"
        print(json.dumps({"status": "failed", "error": message}))
        return 1
    finally:
        if client:
            client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
