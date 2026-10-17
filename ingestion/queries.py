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

SHOP = "query ShopSettings { shop { id ianaTimezone currencyCode taxesIncluded } }"
REFUNDS = """query Refunds($id: ID!) {
 order(id: $id) { refunds { id createdAt updatedAt processedAt totalRefundedSet MONEY } }
}""".replace("MONEY", MONEY)
REFUND_LINES = """query RefundLines($id: ID!, $after: String) {
 refund(id: $id) { refundLineItems(first: 100, after: $after) {
 nodes { id quantity restockType restocked lineItem { id } priceSet MONEY subtotalSet MONEY totalTaxSet MONEY }
 PAGE } }
}""".replace("MONEY", MONEY).replace("PAGE", PAGE)
REFUND_ADJUSTMENTS = """query RefundAdjustments($id: ID!, $after: String) {
 refund(id: $id) { orderAdjustments(first: 100, after: $after) {
 nodes { id amountSet MONEY taxAmountSet MONEY } PAGE } }
}""".replace("MONEY", MONEY).replace("PAGE", PAGE)
# SalesAgreement is not Node-queryable. Keep the outer cursor fixed while
# paginating its sales, then advance exactly one agreement at a time.
AGREEMENTS = """query Agreements($id: ID!, $after: String, $salesAfter: String) {
 order(id: $id) { agreements(first: 1, after: $after) {
 nodes { __typename id happenedAt reason ... on RefundAgreement { refund { id } }
 sales(first: 100, after: $salesAfter) {
 nodes { __typename id actionType lineType quantity totalAmount MONEY
 totalDiscountAmountBeforeTaxes MONEY totalDiscountAmountAfterTaxes MONEY totalTaxAmount MONEY
 ... on ProductSale { lineItem { id } } } PAGE }
 } PAGE } }
}""".replace("MONEY", MONEY).replace("PAGE", PAGE)
