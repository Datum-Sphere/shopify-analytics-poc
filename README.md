# Shopify Analytics POC

Free, Dockerized consulting demonstration. The foundation, read-only ingestion, bounded financial models, and Phase 4A Streamlit/Plotly financial dashboard are implemented. Scheduling and pipeline triggering are not implemented. Financial results are API/fixture validated, not reconciled to a Shopify Analytics report.

## Architecture

Architecture: Shopify Admin GraphQL API (2026-10) → Python ingestion → PostgreSQL 16 → dbt Core + dbt-postgres → Streamlit + Plotly.

- `ingestion/`: OAuth client credentials, read-only GraphQL transport, paginated extractors, JSONB upserts, run audit and CLI.
- `pipeline/`: idle application service and authenticated database health check; future orchestration entry point.
- `dbt/`: environment-based profile, raw staging, product dimension, sales/returns facts, daily mart, financial tests and expected fixture results.
- `dashboard/`: read-only financial dashboard, parameterized database access, Plotly charts and dedicated Dockerfile.
- `tests/`: automated foundation smoke checks.
- `Dockerfile`, `compose.yaml`: Python 3.12 services and persistent PostgreSQL.

## Prerequisites

Docker Desktop running Linux containers with Docker Compose v2+ (tested with Compose v5). On Windows enable the WSL2 backend. Git is needed to clone. No host Python, PostgreSQL, dbt, or paid analytics services are required. Shopify client credentials are required to run ingestion; the dashboard can show synthetic data without them. Internet access is needed for initial image/package downloads. Docker Desktop licensing depends on your organization.

## Start (PowerShell)

```powershell
git clone https://github.com/Datum-Sphere/shopify-analytics-poc.git
cd shopify-analytics-poc
# For a fresh clone only; preserve an existing configured .env.
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Edit .env: set POSTGRES_PASSWORD and a different random DASHBOARD_DB_PASSWORD (20+ characters).
# For ingestion, set the Shopify client ID and secret of your installed app.
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

Open http://localhost:8501 for **Shopify Sales Analytics**. Live Shopify is the default dataset. On a fresh database, complete the data/model setup below before financial figures become available. Containers may take several minutes to build. Wait for all three services to become healthy:

```powershell
docker compose up -d --wait --wait-timeout 180
docker compose exec app dbt debug --project-dir dbt --profiles-dir dbt
docker compose exec app dbt build --project-dir dbt --profiles-dir dbt --select environment_ready
docker compose exec app python -m unittest discover -s tests -v
(Invoke-WebRequest http://localhost:8501/_stcore/health).StatusCode
```

`dbt debug` must report a successful connection. `dbt build --select environment_ready` creates `analytics.environment_ready` and runs not-null, unique, and accepted-value tests. This is a connectivity fixture, not a sales model. dbt uses the official [Postgres profile format](https://docs.getdbt.com/docs/local/connect-data-platform/postgres-setup) and [secret environment variables](https://docs.getdbt.com/reference/dbt-jinja-functions/env_var).

## Security and operations

Streamlit is published on `127.0.0.1:8501` and PostgreSQL on `127.0.0.1:5432` for local DataGrip access. Both ports bind only to the Windows host loopback interface. Containers connect to PostgreSQL through `postgres:5432` on the Compose network. Both Python containers run as non-root. The dashboard receives only its dedicated SELECT-only database password and provides no shell or subprocess controls. Only the app container receives Shopify configuration. Tokens exist only in process memory and are cleared when the client closes; they are never stored in PostgreSQL or files. `.env`, secrets, caches, and dbt output are excluded from Git and Docker build contexts. Never commit credentials. Database credentials are injected at runtime; local Docker administrators can inspect container environment variables. This is a local POC, not production hardening.

PostgreSQL uses the named `postgres_data` volume. `docker compose down` stops the stack and preserves data. `docker compose down -v` **deletes all database data**. Changing database credentials in `.env` does not change an existing database volume's credentials; retain the existing credentials or intentionally reinitialize disposable data. Application code is baked into images: rebuild after edits. dbt artifacts live in the app container and can be inspected with `docker compose exec app dbt ...` or copied with `docker compose cp`.

Troubleshoot with `docker compose ps` and `docker compose logs --tail 100`. Do not publish logs or resolved `docker compose config` output containing credentials. Use `config --quiet` for validation.

## Validation

See [VALIDATION.md](VALIDATION.md) for checks actually executed in the implementation environment. Direct dependencies are pinned in requirements files; transitive dependencies and base image tags can change, so this is not a byte-for-byte locked supply chain.

## DataGrip connection

The standard `compose.yaml` publishes PostgreSQL on localhost; no override file is required. After changing this configuration, apply it with `docker compose up -d`.

| Setting | Value |
| --- | --- |
| Host | `127.0.0.1` |
| Port | `5432` |
| Database | `POSTGRES_DB` from your local `.env` |
| User | `POSTGRES_USER` from your local `.env` |
| Password | `POSTGRES_PASSWORD` from your local `.env` |

Keep credentials in your local client configuration and out of Git. The old optional local port override is no longer needed.

## Phase 2 ingestion

Configure `.env` with `SHOPIFY_STORE_DOMAIN=demo-analytics-poc.myshopify.com`, `SHOPIFY_API_VERSION=2026-10`, and the client ID/secret for installed app `demo-analytics-ingestion`. Never paste secrets into commands or commit `.env`. Client credentials authentication requires an installed app and store in the same Shopify organization; see [Shopify authentication](https://shopify.dev/docs/apps/build/authentication-authorization/client-credentials-grant). No additional permissions are requested. Only `read_products` and `read_orders` are used; granted inventory/customer scopes are unused.

```powershell
docker compose config --quiet
docker compose up --build -d
# Recreate app after changing .env; a plain restart does not reload environment.
docker compose up -d --force-recreate app
docker compose exec -T app python -m ingestion.run --verify-order '#1001'
# Repeat to check idempotency; compare unique_records in both JSON summaries.
docker compose exec -T app python -m ingestion.run --verify-order '#1001'
```

The general CLI is `python -m ingestion.run` inside the app container. Without `--verify-order` it ingests all accessible products and orders. The verification flag separately searches for the exact order name, reports Shopify's `test` flag, and requires the same ID to be ingested. It fails if the exact order is missing. The development-store demonstration order may have `test=false`; this is reported rather than changed. Output contains run IDs, counts, and the verification label, never raw payloads or tokens. Failures return exit code 1 with an application-authored error; provider response bodies and database exceptions are not printed or persisted.

Raw data is stored in `raw.shopify_records` keyed by `(store_domain, entity, source_id)` for products, variants, orders, order line items, payment transactions, refunds, refund lines, sales agreements and sales events. The schema migration adds `is_synthetic` with a false default for existing live rows. Parent IDs link children. Product/order/refund/agreement payloads include their fully paginated child connections; refund headers and transactions are API arrays fetched without truncation. Payload JSON retains every field selected by the explicit allowlists in `ingestion/queries.py`; it does not mean all Shopify fields. Amounts remain decimal strings with shop/presentment currencies. Discounts retain allocation amounts and application indices, methods, targets and values; customer-entered descriptions/codes and customer PII are not queried. Payment metadata includes IDs, kind, status, gateway, amounts and timestamps, without receipts, authorization codes or payment details.

`raw.ingestion_runs` records running/succeeded/failed status, start/end timestamps, processed counts, sanitized errors and order verification. Source writes and successful audit completion commit together. A failed run rolls back its source writes and preserves a failed audit with zero committed counts. A terminated process may leave a `running` audit. Run one CLI process per store at a time.

Inspect only counts and non-PII verification fields:

```powershell
docker compose exec -T postgres psql -U shopify_app -d shopify_analytics -c "SELECT entity, count(*) FROM raw.shopify_records GROUP BY entity ORDER BY entity;"
docker compose exec -T postgres psql -U shopify_app -d shopify_analytics -c "SELECT id, status, started_at, finished_at, row_counts, error, verified_order FROM raw.ingestion_runs ORDER BY id DESC LIMIT 5;"
docker compose exec -T postgres psql -U shopify_app -d shopify_analytics -c "SELECT payload->>'name' AS name, payload->>'test' AS test, jsonb_array_length(payload->'lineItems') AS line_items, jsonb_array_length(payload->'transactions') AS transactions FROM raw.shopify_records WHERE entity='order' AND payload->>'name'='#1001';"
# Substitute POSTGRES_USER/POSTGRES_DB if you configured different values.
```

Validation commands:

```powershell
# Mocked HTTP unit tests plus foundation tests (database tests skip by default).
docker compose exec -T app python -m unittest discover -s tests -v
# Real PostgreSQL tests with mocked Shopify responses; fixtures are cleaned up.
docker compose exec -T -e RUN_DB_TESTS=1 app python -m unittest discover -s tests -p test_ingestion_database.py -v
docker compose exec -T app dbt debug --project-dir dbt --profiles-dir dbt
docker compose exec -T app dbt build --project-dir dbt --profiles-dir dbt --select environment_ready
```

Ingestion is a full scan with cursor pagination for roots and nested connections. Shopify exposes transactions as an array, requested without truncation. Requests have connect/read timeouts, bounded exponential retries for transport errors/429/5xx, Retry-After support, GraphQL throttling retries and token refresh before expiry or once after HTTP 401. GraphQL errors, including partial-data responses, fail the run. API version fallback fails explicitly. By default Shopify exposes only the last 60 days of orders under `read_orders` ([order access](https://shopify.dev/docs/api/admin-graphql/latest/objects/Order)); no historical permission expansion is requested.

Limitations: no incremental watermark, deletion reconciliation, snapshot consistency during concurrent store edits, scheduling, customer extraction, or inventory extraction. Removed child records remain in the separate raw entity history until future reconciliation, while each parent's refreshed payload represents the latest fetched collection. Raw product/line-item titles and SKUs are retained as merchandising fields; do not put customer PII into these fields. This synchronous implementation is for small development stores. Use the run's processed counts versus unique source counts to distinguish work performed from retained rows.

## Phase 3 financial reporting

See [financial definitions and limitations](docs/FINANCIALS.md) for the complete contract and source references. These are product-sales metrics, not cash receipts or accounting revenue recognition. Shopify now calls the broader returns category **sales reversals**. Our `returns_amount` is the positive, discounted, pre-tax merchandise reversal amount; it is not physical-return quantity and not a payment refund.

| Metric | Definition in the supported product-event scope |
| --- | --- |
| Gross sales | Product price × quantity before discounts, taxes and reversals; reconstructed from product ORDER sale events as net merchandise amount + allocated pre-tax discount |
| Discounts | Product discounts on ORDER events, using Shopify's event allocation; excludes compare-at-price and shipping discounts |
| Gross returns | Pre-discount merchandise value reversed on product RETURN events |
| Discounts returned | Discount portion reversed with the returned merchandise |
| Returns (`returns_amount`) | Gross returns − discounts returned, positive amount to subtract |
| Net sales | Gross sales − discounts − returns; excludes taxes, shipping, duties, fees, tips and gift-card issuance |

Sale event net magnitude = `abs(totalAmount.shopMoney.amount) - abs(totalTaxAmount.shopMoney.amount)`. `actionType` determines sale versus reversal direction. Pre-tax discounts use `abs(totalDiscountAmountBeforeTaxes.shopMoney.amount)`. Post-tax discounts, `UPDATE`/unknown product actions, currency mismatches and malformed monetary data are unsupported: quality tests fail and affected daily product totals are null. No fallback substitutes order `totalPrice`, payment transactions or refund-header totals for net sales. Nonzero unclassified/adjustment sale types fail a separate coverage test.

| Relation | Grain |
| --- | --- |
| `stg_orders`, `stg_order_lines`, `stg_refunds`, `stg_refund_lines`, `stg_products`, `stg_sales_agreements`, `stg_sales` | One source ID per store for each entity |
| `dim_product` | One current store/product, with an order-title fallback for missing catalog products |
| `fct_sales_events` | One product Sale ID per store, including test orders marked explicitly |
| `fct_returns` | One product RETURN Sale ID per store, a subset of the event fact |
| `fct_refund_lines` / `fct_refunds` | One refund-line ID / one refund ID per store; audit only |
| `mart_daily_sales` | Dataset flag, store, shop-money currency and store-local agreement date; excludes `test=true` orders |

Reporting date is agreement `happenedAt` converted with the ingested shop `ianaTimezone`. Later reversals appear on their later event date. Refund audit dates use refund `processedAt`, falling back to `createdAt`; they do not replace agreement dates. Decimal amounts use PostgreSQL `numeric`. Presentment values stay in raw JSON; only shop-money values enter facts. Never sum across currencies or dataset flags. The live store uses CAD and America/New_York; host timezone is irrelevant. Pending/unpaid/canceled orders remain in scope; their actual product agreement events determine adjustments.

The ledger is the single metric source. Refund-line subtotals are retained for audit, not added to agreement reversal amounts. Shopify has already allocated discounts to event lines, so the models never redistribute order totals or infer a per-unit refund. Each event joins only unique parent/line keys. Refund children are aggregated before joining their payment header, avoiding one-to-many multiplication.

### Execute and verify

Run these after startup; the full financial build requires the migrated raw tables and financial extraction. The foundation-only build above remains available without Shopify credentials.

```powershell
docker compose up --build -d
docker compose exec -T app python -m ingestion.run --verify-order '#1001'
docker compose exec -T app python -m ingestion.fixtures
docker compose exec -T -e RUN_DB_TESTS=1 app python -m unittest discover -s tests -v
docker compose exec -T app dbt build --project-dir dbt --profiles-dir dbt
# Replay both sources; unique source counts and all financial totals must stay unchanged.
docker compose exec -T app python -m ingestion.run --verify-order '#1001'
docker compose exec -T app python -m ingestion.fixtures
docker compose exec -T app dbt build --project-dir dbt --profiles-dir dbt
# Live figures only:
docker compose exec -T postgres psql -U shopify_app -d shopify_analytics -c "SELECT reporting_date,currency_code,gross_sales,discounts,returns_amount,net_sales FROM analytics.mart_daily_sales WHERE NOT is_synthetic;"
# Fixtures only:
docker compose exec -T postgres psql -U shopify_app -d shopify_analytics -c "SELECT reporting_date,currency_code,gross_sales,discounts,returns_amount,net_sales FROM analytics.mart_daily_sales WHERE is_synthetic ORDER BY currency_code,reporting_date;"
```

Use your configured database/user if different. For a deliberately fixture-free financial build, ingest real data first and use `--vars 'validate_financial_fixtures: false'`. That disables only fixture-expectation assertions; all integrity and financial coverage tests remain enabled. Fixture loading makes no Shopify calls and writes only `is_synthetic=true` records under reserved store `financial-fixtures.invalid`. Expected results are committed separately in `dbt/seeds/expected_daily_sales.csv`.

### Validation boundary

Fixture-validated CAD results: gross **340**, discounts **25**, returns **180**, net **135**. The first partial reversal is one of two units originally priced at 100 with a 10-per-unit discount: gross return 100, discount returned 10, net return 90 on October 4. The second unit reverses on October 6. A shipping refund of 10 and a cash-only refund of 5 do not increase merchandise returns. Refund payment headers total 213, including tax and non-product amounts, so they deliberately differ from returns of 180. Other fixtures test multiple order lines, an unpaid/canceled order, exclusion of a test order, midnight timezone boundaries and separately partitioned USD 7. These are constructed scenarios, not Shopify-exported refund examples.

Live order **#1001**: API-based gross **CAD 200**, discounts **0**, returns **0**, net **CAD 200**, on **2026-10-16** in the shop timezone; Shopify reports `test=false`. The store has no refunds, discount examples, exchanges or order edits to validate their live behavior. The refund query shapes and agreement access were checked against Admin GraphQL 2026-10; `SalesAgreementLineItem` does not exist in that schema. `SalesAgreement.sales` exposes `Sale`/`ProductSale` instead.

**No Shopify Analytics report or ShopifyQL reconciliation was performed.** Report parity for historical changes, price updates, post-tax discounts, tax-inclusive/complex tax scenarios, physical returns, cancellations/edits, fees, and multi-currency conversion remains unverified. Read-orders history is still limited by current permissions. The POC retains all accessible adjustment sale JSON and flags unsupported nonzero adjustments rather than guessing. It does not implement production historical sync, deleted-record reconciliation, or advanced accounting.

## Phase 4A read-only dashboard

The dashboard at http://localhost:8501 offers Live Shopify (default) / Synthetic Demo selection, store selection, currency selection and an inclusive date range. Four KPI cards and three interactive Plotly charts show daily gross/net sales, merchandise reversals and up to ten products by net sales. All views use the same dataset/store/currency/date filters. Store-local reporting dates and existing financial definitions remain unchanged; no FX conversion or independent Python metric formulas are used.

The visible **Run Pipeline & Refresh** button is disabled. Its controlled, authorized backend is deferred to Phase 4B; the dashboard cannot execute ingestion, dbt or shell commands. Filter changes only issue read-only SQL queries. There is no hosting or remote exposure.

### Setup and permissions

Add `DASHBOARD_DB_PASSWORD` to your ignored local `.env`, using a different random password of at least 20 characters from `POSTGRES_PASSWORD`. Fresh-clone placeholders must be replaced. Never paste credentials into command history or commit `.env`.

```powershell
docker compose config --quiet
docker compose up --build -d
# Live data is optional when demonstrating only synthetic data.
docker compose exec -T app python -m ingestion.run --verify-order '#1001'
docker compose exec -T app python -m ingestion.fixtures
docker compose exec -T app dbt build --project-dir dbt --profiles-dir dbt
```

The application startup provisions `shopify_dashboard` on both new and existing database volumes using the existing local bootstrap role. It initializes raw schema structure without running Shopify ingestion. Missing analytics models produce a friendly dashboard readiness message until the financial build completes. Bootstrap requires the role-management privileges provided by the local PostgreSQL image's application user.

Streamlit receives only `DASHBOARD_DB_HOST`, `DASHBOARD_DB_PORT`, `DASHBOARD_DB_NAME` and `DASHBOARD_DB_PASSWORD`; its login name is fixed to `shopify_dashboard`. It receives neither Shopify secrets nor privileged database credentials. The application alone receives the separate password for role provisioning. Password SQL is not logged during provisioning, and exceptions shown by the dashboard are sanitized.

The role has SELECT on exactly these analytics views: `mart_daily_sales`, `fct_sales_events`, `dim_product`, `dashboard_ingestion_status`, and `dashboard_financial_issues`. It has no raw schema access, audit-error access, role membership, write privileges or schema creation privileges. Temporary-table access granted to PUBLIC by PostgreSQL is revoked in this POC database, and public-schema CREATE is disabled. Defaults use read-only transactions; the SQL grants still deny writes if a client disables that default. Explicit dbt model grants preserve access when dbt rebuilds the five views; there is no blanket grant on future tables or raw objects.

For password rotation, update only the local `.env` and recreate the app and Streamlit services. Provisioning is also available through an operator-only CLI:

```powershell
docker compose up -d --force-recreate app streamlit
# Optional operator repair/regrant after an existing-volume setup:
docker compose exec -T app python -m pipeline.dashboard_access
```

Keep the committed bindings `127.0.0.1:5432:5432` (local DataGrip) and `127.0.0.1:8501:8501` on the future demo laptop. Never replace them with unrestricted `5432:5432`, `8501:8501`, or `0.0.0.0` host bindings. The backend app has no published port, the dashboard has no Docker socket, and containers use the private Compose network. The optional ignored host-db override is unnecessary with the current main configuration.

### Data integrity and validation boundary

KPIs sum columns from `mart_daily_sales`; product results first aggregate `fct_sales_events` at product key, then join the tested unique `dim_product`. Product events with no catalog key stay in **Custom / unlinked product**. Identical product titles retain distinct chart keys. Test orders are excluded consistently. Charts use floats only for rendering; database aggregation and KPI formatting preserve PostgreSQL numeric/Decimal amounts.

A selected NULL/unsupported product metric or a matching coverage issue withholds **all** selected financial cards and charts. The UI does not fill NULL with zero or show partial valid totals. The safe quality view also catches unclassified adjustments, missing financial extraction and missing product-event parents, which can be absent from the daily mart. An issue with unknown date or currency blocks the selected source scope conservatively. Issues in a known different period/currency do not contaminate a valid selection. No-data periods display an empty-state message and dashes, not zero sales; calendar gaps are not fabricated.

All financial reads for a rendered selection share a read-only repeatable-read transaction. No application data cache is used. The freshness label is the latest successful ingestion for the selected dataset/store in UTC, independent of the report date range. It is not a dbt-build timestamp or a certification of the latest tests. The metadata view exposes no raw payload, error text or PII.

Dashboard tests cover live **CAD 200** gross/net for the existing #1001 snapshot; full-range synthetic CAD **340 gross, 25 discounts, 180 returns, 135 net**; isolated synthetic USD **7**; and the later-return day **2026-10-04: CAD -90 net**. These are existing ingested API/fixture results. **No Shopify Analytics report reconciliation has been performed.** The dashboard and operator tests do not mutate Shopify or execute a new ingestion automatically.

```powershell
# Run after loading source data and completing the dbt build above.
docker compose exec -T -e RUN_DB_TESTS=1 -e RUN_DASHBOARD_DB_TESTS=1 app python -m unittest discover -s tests -v
docker compose exec -T app dbt build --project-dir dbt --profiles-dir dbt
docker compose ps
(Invoke-WebRequest http://localhost:8501/_stcore/health).Content
```

The dashboard database integration tests explicitly verify the current development-store snapshot and reserved fixtures. Mocked UI/query tests run without database setup; database flags are opt-in. See VALIDATION.md for executed checks and observed limitations.

## Next step

Phase 4B can add a controlled, authorized pipeline-trigger interface. Separately, obtain a Shopify report export and representative real returns/discounts to extend financial reconciliation beyond API and fixture validation.
