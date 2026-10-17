# Shopify Analytics POC

Free, Dockerized consulting demonstration. The foundation and Phase 2 read-only ingestion are implemented. Sales transformations, scheduling, and dashboard business logic are not implemented.

## Architecture

Architecture: Shopify Admin GraphQL API (2026-10) → Python ingestion → PostgreSQL 16 → dbt Core + dbt-postgres → Streamlit + Plotly.

- `ingestion/`: OAuth client credentials, read-only GraphQL transport, paginated extractors, JSONB upserts, run audit and CLI.
- `pipeline/`: idle application service and authenticated database health check; future orchestration entry point.
- `dbt/`: environment-based connection profile, staging/marts directories, and a constant smoke model with three tests.
- `dashboard/`: environment-ready Streamlit page and dedicated Dockerfile.
- `tests/`: automated foundation smoke checks.
- `Dockerfile`, `compose.yaml`: Python 3.12 services and persistent PostgreSQL.

## Prerequisites

Docker Desktop running Linux containers with Docker Compose v2+ (tested with Compose v5). On Windows enable the WSL2 backend. Git is needed to clone. No host Python, PostgreSQL, dbt, or paid analytics services are required. Shopify client credentials are required to run ingestion; the environment-ready page works without them. Internet access is needed for initial image/package downloads. Docker Desktop licensing depends on your organization.

## Start (PowerShell)

```powershell
git clone https://github.com/Datum-Sphere/shopify-analytics-poc.git
cd shopify-analytics-poc
# For a fresh clone only; preserve an existing configured .env.
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Edit .env and replace POSTGRES_PASSWORD with a long random password.
# For ingestion, set the Shopify client ID and secret of your installed app.
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

Open http://localhost:8501. The page displays **Shopify Analytics POC — Environment Ready.** Containers may take several minutes to build. Wait for all three services to become healthy:

```powershell
docker compose up -d --wait --wait-timeout 180
docker compose exec app dbt debug --project-dir dbt --profiles-dir dbt
docker compose exec app dbt build --project-dir dbt --profiles-dir dbt
docker compose exec app python -m unittest discover -s tests -v
(Invoke-WebRequest http://localhost:8501/_stcore/health).StatusCode
```

`dbt debug` must report a successful connection. `dbt build` creates `analytics.environment_ready` and runs not-null, unique, and accepted-value tests. This is a connectivity fixture, not a sales model. dbt uses the official [Postgres profile format](https://docs.getdbt.com/docs/local/connect-data-platform/postgres-setup) and [secret environment variables](https://docs.getdbt.com/reference/dbt-jinja-functions/env_var).

## Security and operations

Only `127.0.0.1:8501` is published to the Windows host; PostgreSQL stays on the Compose network. Both Python containers run as non-root. The dashboard receives no credentials and provides no shell or subprocess controls. Only the app container receives Shopify configuration. Tokens exist only in process memory and are cleared when the client closes; they are never stored in PostgreSQL or files. `.env`, secrets, caches, and dbt output are excluded from Git and Docker build contexts. Never commit credentials. Database credentials are injected at runtime; local Docker administrators can inspect container environment variables. This is a local POC, not production hardening.

PostgreSQL uses the named `postgres_data` volume. `docker compose down` stops the stack and preserves data. `docker compose down -v` **deletes all database data**. Changing database credentials in `.env` does not change an existing database volume's credentials; retain the existing credentials or intentionally reinitialize disposable data. Application code is baked into images: rebuild after edits. dbt artifacts live in the app container and can be inspected with `docker compose exec app dbt ...` or copied with `docker compose cp`.

Troubleshoot with `docker compose ps` and `docker compose logs --tail 100`. Do not publish logs or resolved `docker compose config` output containing credentials. Use `config --quiet` for validation.

## Validation

See [VALIDATION.md](VALIDATION.md) for checks actually executed in the implementation environment. Direct dependencies are pinned in requirements files; transitive dependencies and base image tags can change, so this is not a byte-for-byte locked supply chain.

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

Raw data is stored in `raw.shopify_records` keyed by `(store_domain, entity, source_id)` for products, variants, orders, order line items and order transactions. Parent IDs link children. Product/order payloads include the fully paginated child collections. Payload JSON retains every field selected by the explicit allowlists in `ingestion/queries.py`; it does not mean all Shopify fields. Amounts remain decimal strings with shop/presentment currencies. Discounts retain allocation amounts and application indices, methods, targets and values; customer-entered descriptions/codes and customer PII are not queried. Payment metadata includes IDs, kind, status, gateway, amounts and timestamps, without receipts, authorization codes or payment details.

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
docker compose exec -T app dbt build --project-dir dbt --profiles-dir dbt
```

Ingestion is a full scan with cursor pagination for roots and nested connections. Shopify exposes transactions as an array, requested without truncation. Requests have connect/read timeouts, bounded exponential retries for transport errors/429/5xx, Retry-After support, GraphQL throttling retries and token refresh before expiry or once after HTTP 401. GraphQL errors, including partial-data responses, fail the run. API version fallback fails explicitly. By default Shopify exposes only the last 60 days of orders under `read_orders` ([order access](https://shopify.dev/docs/api/admin-graphql/latest/objects/Order)); no historical permission expansion is requested.

Limitations: no incremental watermark, deletion reconciliation, snapshot consistency during concurrent store edits, scheduling, customer extraction, or inventory extraction. Removed child records remain in the separate raw entity history until future reconciliation, while each parent's refreshed payload represents the latest fetched collection. Raw product/line-item titles and SKUs are retained as merchandising fields; do not put customer PII into these fields. This synchronous implementation is for small development stores. Use the run's processed counts versus unique source counts to distinguish work performed from retained rows.

## Next step

Add dbt staging models and data-quality tests over the raw product/order JSON, agreeing financial definitions before building sales marts or dashboard metrics.
