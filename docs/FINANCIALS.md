# Financial contract and evidence boundary

This POC models a bounded merchandise-sales ledger. It is not a general Shopify report replica or accounting ledger. Fixtures validate the formulas and joins. Live API checks validate only the observed initial order; a Shopify report comparison has not been performed.

## Sources and interpretation

- [Shopify sales-report definitions](https://help.shopify.com/en/manual/reports-and-analytics/shopify-reports/report-types/default-reports/sales-report): product revenue excludes tax/shipping; discounts include line and allocated order discounts; net sales subtracts discounts and reversals. Pending, canceled and unpaid orders are included; test orders are excluded. Shopify now uses sales-reversal terminology, encompassing more than physical returns.
- [SalesAgreement](https://shopify.dev/docs/api/admin-graphql/latest/interfaces/SalesAgreement): order creation, editing and refunding generate dated agreements with itemized sales. Live 2026-10 schema introspection confirmed the interface and its implementations. There is no `SalesAgreementLineItem` type.
- [Sale](https://shopify.dev/docs/api/admin-graphql/latest/interfaces/Sale): totalAmount is after tax and discount; totalTaxAmount is its tax component. Before/after-tax discount allocations are distinct. Shopify's immutable cent allocations are preserved, not recalculated.
- [SaleActionType](https://shopify.dev/docs/api/admin-graphql/latest/enums/SaleActionType): ORDER denotes purchase/charge; RETURN removal/return; UPDATE changes a prior purchase. The POC supports product ORDER/RETURN, retaining UPDATE but failing coverage until its semantics can be separately validated.
- [RefundLineItem](https://shopify.dev/docs/api/admin-graphql/latest/objects/RefundLineItem): item quantity, subtotal, taxes and original line relationship. The refund-line ID is nullable in Shopify's schema; ingestion refuses a missing ID rather than inventing an unstable key.
- [Return/exchange financials](https://shopify.dev/docs/apps/build/orders-fulfillment/returns-apps/read-exchanges): payments need not track merchandise movements one-to-one. Even exchanges can have no additional payment. We do not equate financial reversals with cash refunds or physical restocking.

## Normalization and supported amounts

Preserve signed API amounts in `stg_sales`. For ORDER/RETURN events, normalize monetary component magnitudes with `abs`; `actionType` supplies the financial direction. Let N = abs(totalAmount) − abs(totalTaxAmount), and D = abs(totalDiscountAmountBeforeTaxes). With after-tax discount zero:

| Product action | Gross sales | Discounts | Gross returns | Discounts returned | Returns | Net sales |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ORDER | N + D | D | 0 | 0 | 0 | N |
| RETURN | 0 | 0 | N + D | D | N | −N |

Return values exposed by our facts are positive deductions; this differs from Shopify report columns that display negative reversal values. The identity is gross_sales − discounts − returns_amount = net_sales. Do not subtract both net returns and gross returns, or subtract refunded discounts a second time. Our `discounts` is discounts on sales, not discounts net of reversals; `discounts_returned` is separate.

Money values are decimal currency amounts as supplied by MoneyV2, not integers to divide by 100. No floating-point arithmetic or FX conversion is used. Currency-code equality is required across event money components and the order's recorded shop currency. Synthetic USD in the same fixture store intentionally tests currency partitioning; it is not evidence that the live shop has multiple simultaneous base currencies. Historical changes to shop currency/timezone need a richer history and remain unsupported.

After-tax discounts, unrecognized product actions, missing monetary fields, mismatched currencies and a tax magnitude exceeding its sale total are unsupported; product metrics become null and dbt tests fail. Nonzero AdjustmentSale/UnknownSale events also fail coverage. Shipping, gift-card issuance, taxes, duties, tips and fees are preserved raw but excluded from merchandise metrics. Their raw presence does not make total-sales or cash-flow reporting supported. We deliberately provide no order-line/refund fallback when sales agreements are missing.

## Refund audit and allocation

Refund headers contain `totalRefundedSet`; this is not the product-return metric. Refund lines retain their exact `subtotalSet`, `totalTaxSet`, quantity, source line ID and restock flags. The refund source parent is the order, refund-line parent is the refund, agreement parent is the order, and sale parent is the agreement. RefundAgreement IDs link back to refunds when available. ReturnAgreement events need not link to a refund; all extracted agreement types are retained without querying staff/customer details.

`fct_refunds.payment_less_merchandise_and_tax` is an unexplained audit difference, not an allocation to shipping/goodwill. It can represent shipping, adjustments, fees or timing differences. The synthetic scenario intentionally defines those amounts, but the model never infers their cause for real data. `orderAdjustments` is retained raw with amount/tax and ID; free-text reasons and notes are not queried. Refund shipping/duties and payment success timing are not modeled. No order-level refund is spread across products.

`fct_returns` uses product RETURN events once. `fct_refund_lines` and `fct_refunds` are independent audit facts; adding them to the event ledger would double-count. There is no claim that restocking flags establish physical receipt. A payments-only fixture has no supplied product event, so its cash refund produces no merchandise reversal. This tests separation of inputs, not a claim about every Shopify goodwill-refund event shape.

## Dates, keys and joins

Every key is `store_domain|source_id`, avoiding collisions across stores/datasets. Raw upserts use the existing `(store_domain, entity, source_id)` primary key. `is_synthetic` is explicit and also checked against reserved `.invalid` store names. Facts/views recompute from the unique current raw snapshots, never append monetary aggregates. Replaying fixtures and live ingestion preserves unique counts and every mart value.

Event reporting date is agreement happenedAt in the shop's IANA timezone. Order creation and refund processing timestamps remain audit fields. A later-date refund/reversal does not rewrite the original sale date. The live shop timezone is America/New_York; UTC 2026-10-17 01:18:30 belongs to October 16 there. This date choice is API-based and still requires comparison with report filters/date semantics.

One-to-one joins from sale to agreement, order and source line preserve event grain. Refund-line totals aggregate by refund key before attaching a payment header. No fact joins order headers to both lines and refunds and then sums the multiplied result. `dim_product` is current-state, with missing-catalog title fallback, not a historical product dimension. Null product references remain valid for deleted/custom products; original line IDs remain required for product events.

## Deliberately deferred

No mutation or additional scope is requested. No customer identity, address, email, staff identity, payment receipt, refund note or free-text adjustment reason is extracted. Read-orders history remains bounded by the installed app's current access. No advanced price-update accounting, guaranteed cancellation/reversal report parity, physical-return workflow, historical timezone/currency changes, FX, rounding redistribution, deletion reconciliation, concurrent sync, or accounting revenue recognition is supplied. Tax-inclusive and complex tax scenarios are not exercised by the development store and are not report-reconciled. Future unsupported data should cause a failed financial build, not a guessed metric.
