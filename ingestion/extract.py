"""Paginate roots and every nested connection, preserving all selected JSON fields."""
from ingestion import queries as q
from ingestion.config import IngestionError


def products(client):
    for product in client.paginate(q.PRODUCTS, ("products",)):
        product["variants"] = list(client.paginate(q.VARIANTS, ("product", "variants"), {"id": product["id"]}))
        yield product


def orders(client, search=None):
    shop = client.graphql(q.SHOP)["shop"]
    for order in client.paginate(q.ORDERS, ("orders",), {"search": search}):
        args = {"id": order["id"]}
        order["lineItems"] = list(client.paginate(q.LINES, ("order", "lineItems"), args))
        order["discountApplications"] = list(client.paginate(q.DISCOUNTS, ("order", "discountApplications"), args))
        order["transactions"] = client.graphql(q.TRANSACTIONS, args)["order"]["transactions"]
        order["_shop"] = shop
        order["refunds"] = client.graphql(q.REFUNDS, args)["order"]["refunds"]
        for refund in order["refunds"]:
            refund["refundLineItems"] = list(client.paginate(q.REFUND_LINES, ("refund", "refundLineItems"), {"id": refund["id"]}))
            refund["orderAdjustments"] = list(client.paginate(q.REFUND_ADJUSTMENTS, ("refund", "orderAdjustments"), {"id": refund["id"]}))
            if any(not item.get("id") for item in refund["refundLineItems"]):
                raise IngestionError("refunds: missing source refund-line ID; refusing an unstable upsert key")
        order["agreements"] = list(agreements(client, order["id"]))
        yield order


def agreements(client, order_id):
    outer = None
    seen_outer = set()
    while True:
        args = {"id": order_id, "after": outer, "salesAfter": None}
        connection = client.graphql(q.AGREEMENTS, args)["order"]["agreements"]
        nodes = connection["nodes"]
        if not nodes:
            if connection["pageInfo"]["hasNextPage"]:
                raise IngestionError("agreements: empty advancing page")
            return
        if len(nodes) != 1:
            raise IngestionError("agreements: expected one agreement per outer page")
        agreement = nodes[0]
        sales = agreement["sales"]
        records = list(sales["nodes"])
        seen_sales = set()
        while sales["pageInfo"]["hasNextPage"]:
            cursor = sales["pageInfo"]["endCursor"]
            if not cursor or cursor in seen_sales:
                raise IngestionError("agreements: non-advancing sales cursor")
            seen_sales.add(cursor)
            args["salesAfter"] = cursor
            repeated = client.graphql(q.AGREEMENTS, args)["order"]["agreements"]["nodes"]
            if len(repeated) != 1 or repeated[0]["id"] != agreement["id"]:
                raise IngestionError("agreements: source changed during pagination; retry")
            sales = repeated[0]["sales"]
            records.extend(sales["nodes"])
        agreement["sales"] = records
        yield agreement
        page = connection["pageInfo"]
        if not page["hasNextPage"]:
            return
        outer = page["endCursor"]
        if not outer or outer in seen_outer:
            raise IngestionError("agreements: non-advancing agreement cursor")
        seen_outer.add(outer)
