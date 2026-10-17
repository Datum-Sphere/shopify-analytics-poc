"""Explicit non-customer field allowlists. No customer, address, email or receipt fields."""
PAGE = "pageInfo { hasNextPage endCursor }"
MONEY = "{ shopMoney { amount currencyCode } presentmentMoney { amount currencyCode } }"
PRODUCTS = """query Products($after: String) {
 products(first: 50, after: $after, sortKey: ID) {
 nodes { id legacyResourceId title handle status createdAt updatedAt } PAGE
 }}""".replace("PAGE", PAGE)
VARIANTS = """query Variants($id: ID!, $after: String) {
 product(id: $id) { variants(first: 100, after: $after) {
 nodes { id legacyResourceId title sku price compareAtPrice createdAt updatedAt } PAGE
 }}}""".replace("PAGE", PAGE)
ORDERS = """query Orders($after: String, $search: String) {
 orders(first: 50, after: $after, sortKey: ID, query: $search) {
 nodes { id legacyResourceId name test createdAt updatedAt processedAt cancelledAt closedAt
 currencyCode presentmentCurrencyCode displayFinancialStatus displayFulfillmentStatus
 subtotalPriceSet MONEY totalPriceSet MONEY totalDiscountsSet MONEY totalTaxSet MONEY
 totalShippingPriceSet MONEY currentTotalPriceSet MONEY currentTotalDiscountsSet MONEY
 } PAGE }}""".replace("MONEY", MONEY).replace("PAGE", PAGE)
LINES = """query Lines($id: ID!, $after: String) {
 order(id: $id) { lineItems(first: 100, after: $after) {
 nodes { id title sku quantity currentQuantity variant { id } product { id }
 originalUnitPriceSet MONEY discountedUnitPriceSet MONEY
 discountAllocations { allocatedAmountSet MONEY discountApplication { index } }
 } PAGE }}}""".replace("MONEY", MONEY).replace("PAGE", PAGE)
DISCOUNTS = """query Discounts($id: ID!, $after: String) {
 order(id: $id) { discountApplications(first: 100, after: $after) {
 nodes { __typename index allocationMethod targetSelection targetType
 value { __typename ... on MoneyV2 { amount currencyCode } ... on PricingPercentageValue { percentage } }
 } PAGE }}}""".replace("PAGE", PAGE)
TRANSACTIONS = """query Transactions($id: ID!) {
 order(id: $id) { transactions {
 id kind status gateway test createdAt processedAt amountSet MONEY
 parentTransaction { id }
 }}}""".replace("MONEY", MONEY)
