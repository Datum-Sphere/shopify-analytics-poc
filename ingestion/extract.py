"""Paginate roots and every nested connection, preserving all selected JSON fields."""
from ingestion import queries as q


def products(client):
    for product in client.paginate(q.PRODUCTS, ("products",)):
        product["variants"] = list(client.paginate(q.VARIANTS, ("product", "variants"), {"id": product["id"]}))
        yield product


def orders(client, search=None):
    for order in client.paginate(q.ORDERS, ("orders",), {"search": search}):
        args = {"id": order["id"]}
        order["lineItems"] = list(client.paginate(q.LINES, ("order", "lineItems"), args))
        order["discountApplications"] = list(client.paginate(q.DISCOUNTS, ("order", "discountApplications"), args))
        order["transactions"] = client.graphql(q.TRANSACTIONS, args)["order"]["transactions"]
        yield order
